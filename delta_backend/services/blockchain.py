import asyncio
import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import parse_qsl, urlsplit

from eth_account import Account
from hexbytes import HexBytes
from web3 import AsyncHTTPProvider, AsyncWeb3, Web3
from web3.exceptions import TransactionNotFound
from websockets.asyncio.client import connect

from ..amounts import AmountError, atomic_to_minor, minor_to_atomic, usdt_to_minor
from ..config import Settings
from ..models import SignedTransfer, TransferEvent

logger = logging.getLogger(__name__)
T = TypeVar("T")

ERC20_ABI: list[dict[str, Any]] = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

WS_BACKOFF_SECONDS = (1, 2, 5, 10, 20, 30)
_URL_RE = re.compile(r"(?i)\b(?:https?|wss?)://[^\s'\"<>]+")


def _hex0x(value: bytes | str | HexBytes) -> str:
    rendered = HexBytes(value).hex()
    return rendered if rendered.startswith("0x") else f"0x{rendered}"


def _as_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, (bytes, bytearray, HexBytes)):
        return int.from_bytes(bytes(value), byteorder="big")
    text = str(value)
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def _status_code(exc: BaseException) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        if obj is None:
            continue
        for name in ("status_code", "status"):
            value = getattr(obj, name, None)
            if isinstance(value, int):
                return value
    return None


class BlockchainConfigurationError(RuntimeError):
    pass


class BlockchainRpcError(RuntimeError):
    pass


class BlockchainChainMismatchError(BlockchainConfigurationError):
    pass


class _GetLogsRangeLimitError(BlockchainRpcError):
    pass


@dataclass(frozen=True)
class RpcHealth:
    active_endpoint: str
    chain_id: int
    block_number: int
    primary_ok: bool
    fallback_ok: bool | None
    native_balance_wei: int
    token_balance_atomic: int


@dataclass(frozen=True)
class WebSocketHealth:
    chain_id: int
    block_number: int
    subscription_ok: bool


class EvmTokenClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token_address = Web3.to_checksum_address(settings.token_contract)
        self.treasury_address = Web3.to_checksum_address(settings.treasury_address)
        self._transfer_topic = _hex0x(Web3.keccak(text="Transfer(address,address,uint256)"))
        self._destination_topic = "0x" + self.treasury_address[2:].lower().rjust(64, "0")

        urls = [settings.bsc_rpc_url]
        if settings.bsc_rpc_fallback_url and settings.bsc_rpc_fallback_url not in urls:
            urls.append(settings.bsc_rpc_fallback_url)
        self._http_urls = urls
        self._http_clients = [
            AsyncWeb3(
                AsyncHTTPProvider(
                    url,
                    request_kwargs={"timeout": settings.bsc_rpc_timeout_seconds},
                )
            )
            for url in urls
        ]
        self._preferred_http_index = 0
        self._configured_log_chunk = max(1, int(settings.scan_block_chunk))
        self._adaptive_log_chunk = self._configured_log_chunk
        logger.info(
            "eth_getLogs adaptive chunk initialized: effective=%s configured_ceiling=%s",
            self._adaptive_log_chunk,
            self._configured_log_chunk,
        )

        private_key = self._load_private_key(settings)
        self.account = Account.from_key(private_key) if private_key else None
        if self.account is not None and self.account.address != self.treasury_address:
            raise BlockchainConfigurationError(
                "payout signing account does not match TREASURY_ADDRESS"
            )
        self._secret_fragments = self._collect_secret_fragments()

    @staticmethod
    def _load_private_key(settings: Settings) -> bytes | str:
        if settings.payout_seed_phrase is not None:
            mnemonic = settings.payout_seed_phrase.get_secret_value().strip()
            if mnemonic:
                try:
                    Account.enable_unaudited_hdwallet_features()
                    account = Account.from_mnemonic(
                        mnemonic, account_path=settings.seed_account_path
                    )
                    return account.key
                except Exception as exc:
                    raise BlockchainConfigurationError(
                        "не удалось открыть кошелёк из SEED_PHRASE"
                    ) from exc
        if settings.payout_keystore_path is not None:
            if settings.payout_keystore_password is None:
                raise BlockchainConfigurationError("keystore password is missing")
            try:
                encrypted = json.loads(
                    settings.payout_keystore_path.read_text(encoding="utf-8")
                )
                return Account.decrypt(
                    encrypted, settings.payout_keystore_password.get_secret_value()
                )
            except (OSError, TypeError, ValueError, KeyError) as exc:
                raise BlockchainConfigurationError(
                    "could not decrypt payout keystore"
                ) from exc
        if settings.payout_private_key is not None:
            return settings.payout_private_key.get_secret_value()
        return ""

    def _collect_secret_fragments(self) -> set[str]:
        fragments: set[str] = set()
        for secret in (
            self.settings.payout_seed_phrase.get_secret_value()
            if self.settings.payout_seed_phrase is not None
            else "",
            self.settings.payout_private_key.get_secret_value()
            if self.settings.payout_private_key is not None
            else "",
            self.settings.payout_keystore_password.get_secret_value()
            if self.settings.payout_keystore_password is not None
            else "",
        ):
            secret = secret.strip()
            if secret:
                fragments.add(secret)

        for endpoint in (
            self.settings.bsc_rpc_url,
            self.settings.bsc_rpc_fallback_url,
            self.settings.bsc_wss_url,
        ):
            if not endpoint:
                continue
            parsed = urlsplit(endpoint)
            if parsed.hostname:
                fragments.add(parsed.hostname)
                for label in parsed.hostname.split("."):
                    if len(label) >= 8:
                        fragments.add(label)
            for segment in parsed.path.split("/"):
                if len(segment) >= 8:
                    fragments.add(segment)
            for _, value in parse_qsl(parsed.query, keep_blank_values=False):
                if len(value) >= 8:
                    fragments.add(value)
        return fragments

    def _safe_text(self, value: object, limit: int = 1000) -> str:
        text = str(value)
        for endpoint in (
            self.settings.bsc_rpc_url,
            self.settings.bsc_rpc_fallback_url,
            self.settings.bsc_wss_url,
        ):
            if endpoint:
                text = text.replace(endpoint, "<redacted-rpc-url>")
        for fragment in self._secret_fragments:
            text = text.replace(fragment, "<redacted-api-key>")
        text = _URL_RE.sub("<redacted-rpc-url>", text)
        return text[:limit]

    def safe_error(self, exc: BaseException) -> str:
        status = _status_code(exc)
        message = self._safe_text(exc)
        suffix = f", status={status}" if status is not None else ""
        if message and message != type(exc).__name__:
            return f"{type(exc).__name__}{suffix}: {message}"
        return f"{type(exc).__name__}{suffix}"

    def _contract(self, w3: AsyncWeb3) -> Any:
        return w3.eth.contract(address=self.token_address, abi=ERC20_ABI)

    def _http_order(self) -> list[int]:
        order = [self._preferred_http_index]
        order.extend(i for i in range(len(self._http_clients)) if i not in order)
        return order

    async def _call_http(
        self,
        operation: str,
        call: Callable[[AsyncWeb3], Awaitable[T]],
    ) -> T:
        failures: list[str] = []
        for index in self._http_order():
            label = "primary" if index == 0 else "fallback"
            try:
                result = await call(self._http_clients[index])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                safe = self.safe_error(exc)
                failures.append(f"{label}: {safe}")
                logger.warning("BSC HTTPS RPC %s failed during %s (%s)", label, operation, safe)
                continue
            self._preferred_http_index = index
            return result
        rendered = "; ".join(failures) if failures else "no configured endpoint"
        raise BlockchainRpcError(f"{operation} failed on all HTTPS RPC endpoints: {rendered}")

    async def _check_http_endpoint(self, index: int) -> tuple[int, int]:
        label = "primary" if index == 0 else "fallback"
        w3 = self._http_clients[index]
        try:
            if not await w3.is_connected():
                raise BlockchainRpcError("endpoint is not reachable")
            actual_chain_id = await w3.eth.chain_id
            if actual_chain_id != self.settings.chain_id:
                raise BlockchainChainMismatchError(
                    f"HTTPS RPC {label} returned chainId={actual_chain_id}; "
                    f"expected {self.settings.chain_id}"
                )
            block_number = await w3.eth.block_number
            return actual_chain_id, block_number
        except BlockchainChainMismatchError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise BlockchainRpcError(self.safe_error(exc)) from None

    async def healthcheck(self) -> RpcHealth:
        endpoint_results: dict[int, tuple[int, int]] = {}
        endpoint_errors: dict[int, str] = {}

        for index in range(len(self._http_clients)):
            try:
                endpoint_results[index] = await self._check_http_endpoint(index)
            except BlockchainChainMismatchError:
                # Не оставляем RPC-адрес другой сети в списке для будущего резервного переключения.
                raise
            except BlockchainRpcError as exc:
                endpoint_errors[index] = self._safe_text(exc)

        if not endpoint_results:
            details = "; ".join(
                f"{'primary' if i == 0 else 'fallback'}: {message}"
                for i, message in endpoint_errors.items()
            )
            raise BlockchainConfigurationError(
                f"no HTTPS BSC RPC endpoint passed startup checks ({details})"
            )

        self._preferred_http_index = 0 if 0 in endpoint_results else min(endpoint_results)
        chain_id, block_number = endpoint_results[self._preferred_http_index]

        try:
            actual_decimals = await self._call_http(
                "eth_call decimals()",
                lambda w3: self._contract(w3).functions.decimals().call(),
            )
        except BlockchainRpcError as exc:
            raise BlockchainConfigurationError(
                f"token contract healthcheck failed: {self._safe_text(exc)}"
            ) from None
        if actual_decimals != self.settings.token_decimals:
            raise BlockchainConfigurationError(
                f"token decimals are {actual_decimals}, configured {self.settings.token_decimals}"
            )
        if self.account is None:
            raise BlockchainConfigurationError("payout signing key is missing")

        native_balance = await self.native_balance(self.treasury_address)
        token_balance = await self.token_balance(self.treasury_address)
        minimum_token_atomic = (
            minor_to_atomic(
                usdt_to_minor(self.settings.minimum_token_balance_usdt),
                self.settings.token_decimals,
            )
            if self.settings.minimum_token_balance_usdt > 0
            else 0
        )
        if native_balance < self.settings.minimum_native_balance_wei:
            raise BlockchainConfigurationError(
                "treasury native balance is below MINIMUM_NATIVE_BALANCE_WEI"
            )
        if token_balance < minimum_token_atomic:
            raise BlockchainConfigurationError(
                "treasury token balance is below MINIMUM_TOKEN_BALANCE_USDT"
            )

        # eth_call мог переключиться на резервный RPC, поэтому показываем проверку доступности
        # того RPC-адреса, который реально будет использоваться для следующих операций.
        if self._preferred_http_index in endpoint_results:
            chain_id, block_number = endpoint_results[self._preferred_http_index]

        return RpcHealth(
            active_endpoint="primary" if self._preferred_http_index == 0 else "fallback",
            chain_id=chain_id,
            block_number=block_number,
            primary_ok=0 in endpoint_results,
            fallback_ok=(
                None if len(self._http_clients) == 1 else 1 in endpoint_results
            ),
            native_balance_wei=native_balance,
            token_balance_atomic=token_balance,
        )

    async def latest_block(self) -> int:
        return await self._call_http("eth_blockNumber", lambda w3: w3.eth.block_number)

    async def gas_price(self) -> int:
        return int(await self._call_http("eth_gasPrice", lambda w3: w3.eth.gas_price))

    async def native_balance(self, address: str) -> int:
        checksum = Web3.to_checksum_address(address)
        return await self._call_http(
            "eth_getBalance",
            lambda w3: w3.eth.get_balance(checksum),
        )

    async def token_balance(self, address: str) -> int:
        checksum = Web3.to_checksum_address(address)
        return await self._call_http(
            "eth_call balanceOf()",
            lambda w3: self._contract(w3).functions.balanceOf(checksum).call(),
        )

    async def eth_call(
        self,
        transaction: Mapping[str, Any],
        block_identifier: str | int = "latest",
    ) -> bytes:
        return await self._call_http(
            "eth_call",
            lambda w3: w3.eth.call(dict(transaction), block_identifier=block_identifier),
        )

    def _transfer_from_log(self, log: Mapping[str, Any]) -> TransferEvent | None:
        if log.get("removed") is True:
            return None
        topics = list(log.get("topics") or [])
        if len(topics) < 3:
            return None
        topic0 = _hex0x(topics[0]).lower()
        if topic0 != self._transfer_topic.lower():
            return None

        data = log.get("data", "0x0")
        amount_atomic = _as_int(data)
        try:
            amount_minor = atomic_to_minor(amount_atomic, self.settings.token_decimals)
        except AmountError:
            return None

        from_address = Web3.to_checksum_address("0x" + _hex0x(topics[1])[-40:])
        to_address = Web3.to_checksum_address("0x" + _hex0x(topics[2])[-40:])
        if to_address != self.treasury_address:
            return None

        return TransferEvent(
            chain_id=self.settings.chain_id,
            tx_hash=_hex0x(log["transactionHash"]),
            log_index=_as_int(log["logIndex"]),
            block_number=_as_int(log["blockNumber"]),
            from_address=from_address,
            to_address=to_address,
            amount_atomic=amount_atomic,
            amount_minor=amount_minor,
        )

    def _looks_like_get_logs_range_error(self, exc: BaseException, span: int) -> bool:
        if span <= 1:
            return False
        status = _status_code(exc)
        if status in {400, 413, 422}:
            return True
        text = self._safe_text(exc, limit=1200).lower()
        markers = (
            "block range",
            "blockrange",
            "range too",
            "max range",
            "maximum range",
            "maximum block",
            "exceeds max",
            "too many blocks",
            "query returned more than",
            "response size",
            "too many results",
            "log response size",
            "-32005",
        )
        return any(marker in text for marker in markers)

    async def _fetch_logs_range(self, from_block: int, to_block: int) -> list[Any]:
        span = to_block - from_block + 1
        failures: list[str] = []
        range_failures: list[str] = []
        params = {
            "address": self.token_address,
            "fromBlock": from_block,
            "toBlock": to_block,
            "topics": [self._transfer_topic, None, self._destination_topic],
        }
        for index in self._http_order():
            label = "primary" if index == 0 else "fallback"
            try:
                logs = await self._http_clients[index].eth.get_logs(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                safe = self.safe_error(exc)
                if self._looks_like_get_logs_range_error(exc, span):
                    range_failures.append(f"{label}: {safe}")
                    continue
                failures.append(f"{label}: {safe}")
                logger.warning(
                    "BSC HTTPS RPC %s failed during eth_getLogs (%s)",
                    label,
                    safe,
                )
                continue
            self._preferred_http_index = index
            return list(logs)

        if range_failures:
            raise _GetLogsRangeLimitError("; ".join(range_failures))
        rendered = "; ".join(failures) if failures else "no configured endpoint"
        raise BlockchainRpcError(
            f"eth_getLogs failed on all HTTPS RPC endpoints: {rendered}"
        )

    async def get_incoming_transfers(
        self, from_block: int, to_block: int
    ) -> list[TransferEvent]:
        if to_block < from_block:
            return []

        logs: list[Any] = []
        cursor = from_block
        while cursor <= to_block:
            remaining = to_block - cursor + 1
            span = min(self._adaptive_log_chunk, remaining)
            end_block = cursor + span - 1
            try:
                part = await self._fetch_logs_range(cursor, end_block)
            except _GetLogsRangeLimitError as exc:
                if span <= 1:
                    raise BlockchainRpcError(
                        "eth_getLogs was rejected even for a single block: "
                        + self._safe_text(exc)
                    ) from None
                reduced = max(1, span // 2)
                old = self._adaptive_log_chunk
                self._adaptive_log_chunk = min(old, reduced)
                logger.info(
                    "eth_getLogs range was rejected; adaptive block chunk reduced "
                    "from %s to %s",
                    old,
                    self._adaptive_log_chunk,
                )
                continue
            logs.extend(part)
            cursor = end_block + 1

        transfers: list[TransferEvent] = []
        for log in logs:
            transfer = self._transfer_from_log(log)
            if transfer is not None:
                transfers.append(transfer)
        return transfers

    @property
    def adaptive_log_chunk(self) -> int:
        return self._adaptive_log_chunk

    async def sign_token_transfer(self, address: str, amount_minor: int) -> SignedTransfer:
        if self.account is None:
            raise BlockchainConfigurationError("payout signing key is missing")
        destination = Web3.to_checksum_address(address)
        value_atomic = minor_to_atomic(amount_minor, self.settings.token_decimals)

        async def build(w3: AsyncWeb3) -> SignedTransfer:
            contract = self._contract(w3)
            nonce = await w3.eth.get_transaction_count(self.account.address, "pending")
            function = contract.functions.transfer(destination, value_atomic)
            gas_estimate = await function.estimate_gas({"from": self.account.address})
            gas_price = await w3.eth.gas_price
            transaction = await function.build_transaction(
                {
                    "from": self.account.address,
                    "chainId": self.settings.chain_id,
                    "nonce": nonce,
                    "gas": gas_estimate * 120 // 100,
                    "gasPrice": gas_price,
                }
            )
            signed = self.account.sign_transaction(transaction)
            return SignedTransfer(
                tx_hash=_hex0x(signed.hash),
                raw_transaction=_hex0x(signed.raw_transaction),
                nonce=nonce,
            )

        return await self._call_http(
            "eth_getTransactionCount/eth_estimateGas/eth_gasPrice",
            build,
        )

    async def broadcast(self, raw_transaction: str) -> str:
        tx_hash = await self._call_http(
            "eth_sendRawTransaction",
            lambda w3: w3.eth.send_raw_transaction(HexBytes(raw_transaction)),
        )
        return _hex0x(tx_hash)

    async def receipt_status(self, tx_hash: str) -> bool | None:
        failures: list[str] = []
        not_found = 0
        for index in self._http_order():
            label = "primary" if index == 0 else "fallback"
            try:
                receipt = await self._http_clients[index].eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                not_found += 1
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                safe = self.safe_error(exc)
                failures.append(f"{label}: {safe}")
                logger.warning(
                    "BSC HTTPS RPC %s failed during eth_getTransactionReceipt (%s)",
                    label,
                    safe,
                )
                continue
            self._preferred_http_index = index
            return bool(receipt["status"])

        if not_found == len(self._http_clients):
            return None
        if failures and not_found + len(failures) == len(self._http_clients):
            raise BlockchainRpcError(
                "eth_getTransactionReceipt failed: " + "; ".join(failures)
            )
        return None

    async def signer_balances(self) -> tuple[int, int]:
        if self.account is None:
            return (0, 0)
        native = await self.native_balance(self.account.address)
        token = await self.token_balance(self.account.address)
        return (native, token)

    def _ws_connect(self) -> Any:
        return connect(
            self.settings.bsc_wss_url,
            open_timeout=self.settings.bsc_wss_open_timeout_seconds,
            ping_interval=self.settings.bsc_wss_ping_interval_seconds,
            ping_timeout=self.settings.bsc_wss_ping_timeout_seconds,
            close_timeout=10,
            max_queue=1024,
        )

    async def _ws_rpc_request(
        self,
        websocket: Any,
        request_id: int,
        method: str,
        params: list[Any],
    ) -> Any:
        await websocket.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
        )
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=self.settings.bsc_wss_rpc_timeout_seconds,
                )
            except TimeoutError as exc:
                raise BlockchainRpcError(f"{method} WebSocket response timed out") from exc
            message = json.loads(raw)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"] or {}
                code = error.get("code", "unknown")
                detail = self._safe_text(error.get("message", "JSON-RPC error"), limit=300)
                raise BlockchainRpcError(f"{method} JSON-RPC error {code}: {detail}")
            return message.get("result")

    def _subscription_params(self) -> list[Any]:
        return [
            "logs",
            {
                "address": self.token_address,
                "topics": [self._transfer_topic, None, self._destination_topic],
            },
        ]

    async def websocket_healthcheck(self) -> WebSocketHealth:
        try:
            async with self._ws_connect() as websocket:
                chain_hex = await self._ws_rpc_request(
                    websocket, 1, "eth_chainId", []
                )
                chain_id = _as_int(chain_hex)
                if chain_id != self.settings.chain_id:
                    raise BlockchainChainMismatchError(
                        f"WebSocket returned chainId={chain_id}; expected {self.settings.chain_id}"
                    )
                block_hex = await self._ws_rpc_request(
                    websocket, 2, "eth_blockNumber", []
                )
                subscription_id = await self._ws_rpc_request(
                    websocket, 3, "eth_subscribe", self._subscription_params()
                )
                if not subscription_id:
                    raise BlockchainConfigurationError(
                        "WebSocket eth_subscribe returned an empty subscription id"
                    )
                await self._ws_rpc_request(
                    websocket, 4, "eth_unsubscribe", [subscription_id]
                )
                return WebSocketHealth(
                    chain_id=chain_id,
                    block_number=_as_int(block_hex),
                    subscription_ok=True,
                )
        except BlockchainConfigurationError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise BlockchainConfigurationError(
                f"WebSocket startup check failed: {self.safe_error(exc)}"
            ) from None

    async def stream_incoming_transfers(
        self,
        stop_event: asyncio.Event,
        on_subscribed: Callable[[], Awaitable[None]] | None = None,
        on_head: Callable[[int], Awaitable[None] | None] | None = None,
        on_removed: Callable[[str, int], Awaitable[None] | None] | None = None,
    ) -> AsyncIterator[TransferEvent]:
        """Stream token logs immediately and use newHeads as the confirmation clock.

        HTTPS backfill starts in the background after subscriptions are active, so a
        large free-tier backfill cannot block real-time WebSocket message handling.
        """
        backoff_index = 0
        loop = asyncio.get_running_loop()

        async def run_backfill(callback: Callable[[], Awaitable[None]]) -> None:
            try:
                await callback()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "HTTPS backfill after WebSocket connect failed; "
                    "WebSocket remains active (%s)",
                    self.safe_error(exc),
                )

        async def call_optional(callback: Any, *args: Any) -> None:
            if callback is None:
                return
            try:
                result = callback(*args)
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "BSC WebSocket callback failed (%s)",
                    self.safe_error(exc),
                )

        while not stop_event.is_set():
            connected_at: float | None = None
            backfill_task: asyncio.Task[None] | None = None
            try:
                async with self._ws_connect() as websocket:
                    connected_at = loop.time()
                    chain_hex = await self._ws_rpc_request(
                        websocket, 99, "eth_chainId", []
                    )
                    chain_id = _as_int(chain_hex)
                    if chain_id != self.settings.chain_id:
                        raise BlockchainChainMismatchError(
                            f"WebSocket returned chainId={chain_id}; "
                            f"expected {self.settings.chain_id}"
                        )

                    head_subscription_id: str | None = None
                    try:
                        head_subscription_id = await self._ws_rpc_request(
                            websocket,
                            100,
                            "eth_subscribe",
                            ["newHeads"],
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(
                            "BSC WebSocket newHeads subscription unavailable; "
                            "HTTPS confirmation fallback will be used (%s)",
                            self.safe_error(exc),
                        )

                    subscription_id = await self._ws_rpc_request(
                        websocket,
                        101,
                        "eth_subscribe",
                        self._subscription_params(),
                    )
                    if not subscription_id:
                        raise BlockchainRpcError("eth_subscribe returned empty subscription id")
                    logger.info(
                        "BSC WebSocket connected; Transfer subscription is active; "
                        "newHeads=%s",
                        bool(head_subscription_id),
                    )

                    if on_subscribed is not None:
                        backfill_task = asyncio.create_task(
                            run_backfill(on_subscribed),
                            name="deposit-wss-backfill",
                        )

                    try:
                        async for raw in websocket:
                            if stop_event.is_set():
                                return
                            message = json.loads(raw)
                            if message.get("method") != "eth_subscription":
                                continue
                            params = message.get("params") or {}
                            current_subscription = params.get("subscription")
                            result = params.get("result")

                            if (
                                head_subscription_id
                                and current_subscription == head_subscription_id
                            ):
                                if isinstance(result, Mapping) and result.get("number") is not None:
                                    await call_optional(on_head, _as_int(result["number"]))
                                continue

                            if current_subscription != subscription_id:
                                continue
                            if not isinstance(result, Mapping):
                                continue

                            if result.get("removed") is True:
                                tx_hash = result.get("transactionHash")
                                log_index = result.get("logIndex")
                                if tx_hash is not None and log_index is not None:
                                    await call_optional(
                                        on_removed,
                                        _hex0x(tx_hash),
                                        _as_int(log_index),
                                    )
                                continue

                            transfer = self._transfer_from_log(result)
                            if transfer is not None:
                                yield transfer
                    finally:
                        if backfill_task is not None and not backfill_task.done():
                            backfill_task.cancel()
                            await asyncio.gather(backfill_task, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                lifetime = (
                    loop.time() - connected_at if connected_at is not None else 0.0
                )
                if lifetime >= 30:
                    backoff_index = 0
                delay = WS_BACKOFF_SECONDS[min(backoff_index, len(WS_BACKOFF_SECONDS) - 1)]
                backoff_index = min(backoff_index + 1, len(WS_BACKOFF_SECONDS) - 1)
                status = _status_code(exc)
                status_text = f", status={status}" if status is not None else ""
                logger.warning(
                    "BSC WebSocket disconnected (%s%s); reconnect in %ss",
                    type(exc).__name__,
                    status_text,
                    delay,
                )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass

    async def close(self) -> None:
        for w3 in self._http_clients:
            disconnect = getattr(w3.provider, "disconnect", None)
            if disconnect is None:
                continue
            try:
                result = disconnect()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # Ошибка при завершении соединения не должна скрывать исходную причину остановки приложения.
                pass

    @property
    def signer_address(self) -> str | None:
        return self.account.address if self.account is not None else None
