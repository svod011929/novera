import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from ..backup import backup_database
from ..config import Settings
from ..repository import DeltaRepository
from .blockchain import EvmTokenClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SafetyRuntime:
    started_at: float = field(default_factory=time.time)
    last_check_at: float | None = None
    last_check_error: str | None = None
    status: str = "initializing"
    circuit_open: bool = False
    circuit_reasons: list[str] = field(default_factory=list)
    chain_head: int | None = None
    rpc_ok: bool | None = None
    native_balance_wei: int | None = None
    token_balance_minor: int | None = None
    payout_pending_count: int = 0
    payout_pending_minor: int = 0
    next_queued_minor: int = 0
    oldest_payout_age_seconds: int | None = None
    last_payout_confirmed_at: int | None = None
    wss_last_head: int | None = None
    wss_last_head_at: float | None = None
    http_last_scan_at: float | None = None
    http_last_head: int | None = None
    db_integrity: str = "unknown"
    db_integrity_checked_at: float | None = None
    last_backup_at: float | None = None
    last_backup_path: str | None = None
    last_backup_sha256: str | None = None
    last_backup_error: str | None = None
    active_alerts: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, object]:
        result = asdict(self)
        result["uptime_seconds"] = int(time.time() - self.started_at)
        if self.wss_last_head_at is not None:
            result["wss_head_age_seconds"] = max(0, int(time.time() - self.wss_last_head_at))
        else:
            result["wss_head_age_seconds"] = None
        if self.http_last_scan_at is not None:
            result["http_scan_age_seconds"] = max(0, int(time.time() - self.http_last_scan_at))
        else:
            result["http_scan_age_seconds"] = None
        return result


class PayoutCircuitBreaker:
    """Runtime-only payout signing guard.

    It never mutates PAYOUTS_ENABLED. Existing signed/broadcast transactions can still
    be reconciled while new queued payouts remain untouched until conditions recover.
    """

    def __init__(self, runtime: SafetyRuntime) -> None:
        self.runtime = runtime
        # Fail closed for NEW signatures until the first safety pass completes.
        self.set_reasons(["SAFETY_STARTUP"])

    @property
    def is_open(self) -> bool:
        return bool(self.runtime.circuit_open)

    def set_reasons(self, reasons: list[str]) -> None:
        normalized = sorted({str(item) for item in reasons if item})
        self.runtime.circuit_reasons = normalized
        self.runtime.circuit_open = bool(normalized)

    def add_reason(self, reason: str) -> None:
        self.set_reasons([*self.runtime.circuit_reasons, reason])


class SafetyMonitor:
    ALERT_STATE_KEY = "v10.4:active_alerts"

    def __init__(
        self,
        repository: DeltaRepository,
        settings: Settings,
        chain: EvmTokenClient | None,
        bot_token: str,
        runtime: SafetyRuntime,
        circuit: PayoutCircuitBreaker,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.chain = chain
        self.runtime = runtime
        self.circuit = circuit
        self.bot = Bot(bot_token)
        self._last_integrity_check = 0.0
        self._last_backup_attempt = 0.0
        self._backup_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.bot.session.close()

    @staticmethod
    def _token_atomic_to_minor_floor(value_atomic: int, token_decimals: int) -> int:
        if value_atomic <= 0:
            return 0
        if token_decimals >= 6:
            return value_atomic // (10 ** (token_decimals - 6))
        return value_atomic * (10 ** (6 - token_decimals))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _backup_destination(self) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        return Path(self.settings.database_path).parent.parent / "backups" / f"novera-safety-{stamp}.sqlite3"

    def _prune_backups(self, root: Path) -> None:
        keep = max(1, int(self.settings.safety_backup_retention_count))
        items = sorted(root.glob("novera-safety-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in items[keep:]:
            try:
                checksum = path.with_suffix(path.suffix + ".sha256")
                runtime_bundle = path.with_name(f"{path.stem}.runtime-config.enc")
                path.unlink(missing_ok=True)
                checksum.unlink(missing_ok=True)
                runtime_bundle.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not prune safety backup: %s", path.name)

    def _create_backup_sync(self) -> tuple[Path, str]:
        destination = self._backup_destination()
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_database(Path(self.settings.database_path), destination)
        digest = self._sha256(destination)
        manifest_lines = [f"{digest}  {destination.name}"]
        runtime_source = (
            Path(self.settings.database_path).parent
            / "runtime_secrets"
            / "active.enc"
        )
        if runtime_source.is_file():
            runtime_destination = destination.with_name(
                f"{destination.stem}.runtime-config.enc"
            )
            temporary = runtime_destination.with_name(
                f".{runtime_destination.name}.{uuid.uuid4().hex}.tmp"
            )
            try:
                shutil.copyfile(runtime_source, temporary)
                temporary.chmod(0o640)
                os.replace(temporary, runtime_destination)
            finally:
                temporary.unlink(missing_ok=True)
            manifest_lines.append(
                f"{self._sha256(runtime_destination)}  {runtime_destination.name}"
            )
        checksum = destination.with_suffix(destination.suffix + ".sha256")
        checksum.write_text("\n".join(manifest_lines) + "\n", encoding="ascii")
        destination.chmod(0o640)
        checksum.chmod(0o640)
        self._prune_backups(destination.parent)
        return destination, digest

    async def _create_backup(self) -> None:
        async with self._backup_lock:
            self._last_backup_attempt = time.time()
            try:
                path, digest = await asyncio.to_thread(self._create_backup_sync)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.runtime.last_backup_error = type(exc).__name__
                logger.exception("NOVERA safety backup failed")
                return
            self.runtime.last_backup_at = time.time()
            self.runtime.last_backup_path = path.name
            self.runtime.last_backup_sha256 = digest
            self.runtime.last_backup_error = None

    async def _integrity_check(self) -> None:
        now = time.time()
        if now - self._last_integrity_check < max(300, int(self.settings.safety_integrity_interval_seconds)):
            return
        self._last_integrity_check = now
        try:
            result = await self.repository.database_quick_check()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.runtime.db_integrity = f"error:{type(exc).__name__}"
        else:
            self.runtime.db_integrity = result
        self.runtime.db_integrity_checked_at = time.time()

    async def _admin_ids(self) -> set[int]:
        try:
            dynamic = await self.repository.granted_admin_ids()
        except Exception:
            dynamic = set()
        return set(self.settings.admin_id_set) | dynamic

    async def _send_admin(self, text: str) -> None:
        for admin_id in sorted(await self._admin_ids()):
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except TelegramRetryAfter as exc:
                await asyncio.sleep(min(float(exc.retry_after), 5.0))
            except (TelegramForbiddenError, TelegramBadRequest):
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Safety alert delivery failed: admin=%s error=%s", admin_id, type(exc).__name__)

    def _alert_text(self, code: str, recovered: bool = False) -> str:
        prefix = "✅ <b>NOVERA Safety: восстановлено</b>" if recovered else "🚨 <b>NOVERA Safety</b>"
        details = {
            "LOW_BNB": "Недостаточный резерв BNB для безопасного выполнения новых выплат.",
            "LOW_USDT": "USDT на treasury меньше суммы текущих необработанных обязательств.",
            "RPC_UNAVAILABLE": "BSC HTTPS RPC недоступен. Новые выплаты временно не подписываются.",
            "PAYOUT_STUCK": "Есть подписанная или отправленная выплата, которая слишком долго не получает финальный статус.",
            "WSS_STALE": "Alchemy WSS давно не присылал новый head. HTTP backfill продолжает работать.",
            "HTTP_SCAN_STALE": "HTTP backfill депозитов давно не подтверждал успешный проход.",
            "DB_INTEGRITY": "Проверка SQLite quick_check не вернула ok.",
            "BACKUP_STALE": "Давно не было подтверждённого safety-backup.",
            "BACKUP_FAILED": "Последняя попытка safety-backup завершилась ошибкой.",
        }.get(code, code)
        if code == "LOW_USDT":
            suffix = "\nЕсли не хватает средств на следующую выплату, новые подписи временно приостанавливаются."
        elif code in {"LOW_BNB", "RPC_UNAVAILABLE", "PAYOUT_STUCK", "DB_INTEGRITY"}:
            suffix = "\nАвтоматическая блокировка снимается после восстановления условий."
        else:
            suffix = ""
        return f"{prefix}\n\n<b>{code}</b>\n{details}{suffix}"

    async def _publish_transitions(self, alerts: set[str]) -> None:
        previous_raw = await self.repository.get_safety_state(self.ALERT_STATE_KEY)
        previous: set[str] = set()
        if previous_raw:
            try:
                data = json.loads(previous_raw)
                if isinstance(data, list):
                    previous = {str(item) for item in data}
            except (TypeError, ValueError, json.JSONDecodeError):
                previous = set()
        activated = sorted(alerts - previous)
        recovered = sorted(previous - alerts)
        for code in activated:
            await self._send_admin(self._alert_text(code, recovered=False))
        for code in recovered:
            await self._send_admin(self._alert_text(code, recovered=True))
        if alerts != previous:
            await self.repository.set_safety_state(self.ALERT_STATE_KEY, json.dumps(sorted(alerts)))

    async def _chain_snapshot(self) -> tuple[set[str], list[str]]:
        alerts: set[str] = set()
        blockers: list[str] = []
        if self.chain is None or not self.settings.chain_enabled:
            self.runtime.rpc_ok = None
            return alerts, blockers
        try:
            head = await self.chain.latest_block()
            native, token_atomic = await self.chain.signer_balances()
            gas_price = await self.chain.gas_price()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.runtime.rpc_ok = False
            self.runtime.last_check_error = self.chain.safe_error(exc)
            alerts.add("RPC_UNAVAILABLE")
            blockers.append("RPC_UNAVAILABLE")
            return alerts, blockers

        self.runtime.rpc_ok = True
        self.runtime.chain_head = int(head)
        self.runtime.native_balance_wei = int(native)
        self.runtime.token_balance_minor = self._token_atomic_to_minor_floor(
            int(token_atomic), int(self.settings.token_decimals)
        )

        # Conservative floor: enough BNB for at least one ordinary BEP-20 transfer,
        # plus the explicit operator-configured reserve.
        dynamic_fee_floor = int(gas_price) * 120_000
        required_native = max(int(self.settings.safety_min_native_balance_wei), dynamic_fee_floor)
        if int(native) < required_native:
            alerts.add("LOW_BNB")
            blockers.append("LOW_BNB")

        token_minor = int(self.runtime.token_balance_minor or 0)
        if self.runtime.payout_pending_minor > 0 and token_minor < self.runtime.payout_pending_minor:
            alerts.add("LOW_USDT")
        if self.runtime.next_queued_minor > 0 and token_minor < self.runtime.next_queued_minor:
            blockers.append("LOW_USDT")

        return alerts, blockers

    def _telemetry_alerts(self) -> tuple[set[str], list[str]]:
        alerts: set[str] = set()
        blockers: list[str] = []
        now = time.time()
        grace = max(60, int(self.settings.safety_startup_grace_seconds))
        if now - self.runtime.started_at >= grace and self.settings.chain_enabled:
            wss_age = None if self.runtime.wss_last_head_at is None else now - self.runtime.wss_last_head_at
            if wss_age is None or wss_age > int(self.settings.safety_wss_stale_seconds):
                alerts.add("WSS_STALE")
            http_age = None if self.runtime.http_last_scan_at is None else now - self.runtime.http_last_scan_at
            if http_age is None or http_age > int(self.settings.safety_http_scan_stale_seconds):
                alerts.add("HTTP_SCAN_STALE")

        if self.runtime.oldest_payout_age_seconds is not None and self.runtime.oldest_payout_age_seconds > int(self.settings.safety_payout_stuck_seconds):
            alerts.add("PAYOUT_STUCK")
            blockers.append("PAYOUT_STUCK")

        if self.runtime.db_integrity != "ok":
            alerts.add("DB_INTEGRITY")
            blockers.append("DB_INTEGRITY")

        backup_age = None if self.runtime.last_backup_at is None else now - self.runtime.last_backup_at
        stale_after = max(
            int(self.settings.safety_backup_interval_seconds) * 2,
            int(self.settings.safety_backup_stale_seconds),
        )
        if now - self.runtime.started_at >= grace and (backup_age is None or backup_age > stale_after):
            alerts.add("BACKUP_STALE")
        if self.runtime.last_backup_error:
            alerts.add("BACKUP_FAILED")
        return alerts, blockers

    async def run_once(self) -> None:
        self.runtime.last_check_at = time.time()
        self.runtime.last_check_error = None
        metrics = await self.repository.payout_safety_metrics()
        self.runtime.payout_pending_count = int(metrics["pending_count"])
        self.runtime.payout_pending_minor = int(metrics["pending_minor"])
        self.runtime.next_queued_minor = int(metrics["next_queued_minor"] or 0)
        self.runtime.oldest_payout_age_seconds = metrics["oldest_age_seconds"]
        self.runtime.last_payout_confirmed_at = metrics["last_confirmed_at"]

        await self._integrity_check()
        now = time.time()
        if (
            self.runtime.last_backup_at is None
            or now - self.runtime.last_backup_at >= int(self.settings.safety_backup_interval_seconds)
        ) and now - self._last_backup_attempt >= min(300, int(self.settings.safety_backup_interval_seconds)):
            await self._create_backup()

        alerts, blockers = await self._chain_snapshot()
        extra_alerts, extra_blockers = self._telemetry_alerts()
        alerts |= extra_alerts
        blockers.extend(extra_blockers)
        self.circuit.set_reasons(blockers)
        self.runtime.active_alerts = sorted(alerts)
        self.runtime.status = "degraded" if alerts else "ok"
        await self._publish_transitions(alerts)

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.runtime.last_check_error = type(exc).__name__
                    self.runtime.status = "error"
                    self.circuit.add_reason("SAFETY_MONITOR_ERROR")
                    logger.exception("NOVERA safety monitor failed")
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=max(10, int(self.settings.safety_check_interval_seconds)),
                    )
                except TimeoutError:
                    pass
        finally:
            await self.close()
