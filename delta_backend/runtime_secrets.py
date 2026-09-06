from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from Crypto.Cipher import AES


_AAD = b"NOVERA-RUNTIME-CHAIN-CONFIG-v1"
_GENERATION_RE = re.compile(r"^[a-f0-9]{32}$")
_MAX_BUNDLE_BYTES = 32_768
_MAX_KEY_BYTES = 1024


class RuntimeSecretError(RuntimeError):
    """Safe runtime-secret failure that never includes secret material."""


@dataclass(frozen=True, slots=True, repr=False)
class ChainSecretBundle:
    generation: str
    created_at: int
    mode: str
    chain_id: int
    rpc_url: str
    wss_url: str
    seed_phrase: str
    token_contract: str
    treasury_address: str
    scan_start_block: int

    @classmethod
    def create(
        cls,
        *,
        mode: str,
        chain_id: int,
        rpc_url: str,
        wss_url: str,
        seed_phrase: str,
        token_contract: str,
        treasury_address: str,
        scan_start_block: int,
    ) -> ChainSecretBundle:
        bundle = cls(
            generation=uuid.uuid4().hex,
            created_at=int(time.time()),
            mode=mode,
            chain_id=int(chain_id),
            rpc_url=rpc_url.strip(),
            wss_url=wss_url.strip(),
            seed_phrase=" ".join(seed_phrase.split()),
            token_contract=token_contract.strip(),
            treasury_address=treasury_address.strip(),
            scan_start_block=int(scan_start_block),
        )
        bundle.validate()
        return bundle

    @classmethod
    def from_payload(cls, payload: object) -> ChainSecretBundle:
        if not isinstance(payload, dict):
            raise RuntimeSecretError("Encrypted chain configuration is malformed")
        try:
            bundle = cls(
                generation=str(payload["generation"]),
                created_at=int(payload["created_at"]),
                mode=str(payload["mode"]),
                chain_id=int(payload["chain_id"]),
                rpc_url=str(payload["rpc_url"]),
                wss_url=str(payload["wss_url"]),
                seed_phrase=str(payload["seed_phrase"]),
                token_contract=str(payload["token_contract"]),
                treasury_address=str(payload["treasury_address"]),
                scan_start_block=int(payload["scan_start_block"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeSecretError("Encrypted chain configuration is malformed") from exc
        bundle.validate()
        return bundle

    def validate(self) -> None:
        if not _GENERATION_RE.fullmatch(self.generation):
            raise RuntimeSecretError("Invalid chain configuration generation")
        if self.mode not in {"production", "testnet"}:
            raise RuntimeSecretError("Invalid chain configuration mode")
        expected_chain = 56 if self.mode == "production" else 97
        if self.chain_id != expected_chain:
            raise RuntimeSecretError("Chain configuration network mismatch")
        if not 1 <= len(self.rpc_url) <= 4096 or not 1 <= len(self.wss_url) <= 4096:
            raise RuntimeSecretError("Chain provider configuration is missing")
        if not 1 <= len(self.seed_phrase) <= 512:
            raise RuntimeSecretError("Chain signing configuration is missing")
        if len(self.token_contract) != 42 or len(self.treasury_address) != 42:
            raise RuntimeSecretError("Chain address configuration is invalid")
        if self.scan_start_block < 0:
            raise RuntimeSecretError("Chain scan start block is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "created_at": self.created_at,
            "mode": self.mode,
            "chain_id": self.chain_id,
            "rpc_url": self.rpc_url,
            "wss_url": self.wss_url,
            "seed_phrase": self.seed_phrase,
            "token_contract": self.token_contract,
            "treasury_address": self.treasury_address,
            "scan_start_block": self.scan_start_block,
        }

    @property
    def public_fingerprint(self) -> str:
        value = "|".join(
            (
                self.mode,
                str(self.chain_id),
                self.token_contract.lower(),
                self.treasury_address.lower(),
                str(self.scan_start_block),
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def __repr__(self) -> str:
        return (
            "ChainSecretBundle("
            f"generation={self.generation!r}, mode={self.mode!r}, "
            f"chain_id={self.chain_id}, public_fingerprint={self.public_fingerprint!r})"
        )


class RuntimeSecretStore:
    """Versioned authenticated-encryption store for runtime chain configuration."""

    def __init__(self, root: Path, key_file: Path) -> None:
        self.root = Path(root)
        self.key_file = Path(key_file)
        self.active_path = self.root / "active.enc"
        self.previous_path = self.root / "previous.enc"

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    def _read_key(self) -> bytes:
        try:
            if not self.key_file.is_file() or self.key_file.stat().st_size > _MAX_KEY_BYTES:
                raise RuntimeSecretError("Runtime configuration key is unavailable")
            encoded = self.key_file.read_text(encoding="ascii").strip()
            key = base64.b64decode(encoded, validate=True)
        except RuntimeSecretError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuntimeSecretError("Runtime configuration key is unavailable") from exc
        if len(key) != 32:
            raise RuntimeSecretError("Runtime configuration key is invalid")
        return key

    def _encrypt(self, bundle: ChainSecretBundle) -> bytes:
        plaintext = json.dumps(
            bundle.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(plaintext) > _MAX_BUNDLE_BYTES:
            raise RuntimeSecretError("Chain configuration is too large")
        nonce = secrets.token_bytes(12)
        cipher = AES.new(self._read_key(), AES.MODE_GCM, nonce=nonce, mac_len=16)
        cipher.update(_AAD)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        envelope = {
            "algorithm": "AES-256-GCM",
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
            "version": 1,
        }
        return (
            json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("ascii")
            + b"\n"
        )

    def _decrypt(self, value: bytes) -> ChainSecretBundle:
        if not value or len(value) > _MAX_BUNDLE_BYTES:
            raise RuntimeSecretError("Encrypted chain configuration is invalid")
        try:
            envelope = json.loads(value.decode("ascii"))
            if (
                not isinstance(envelope, dict)
                or envelope.get("version") != 1
                or envelope.get("algorithm") != "AES-256-GCM"
            ):
                raise ValueError("unsupported envelope")
            nonce = base64.b64decode(str(envelope["nonce"]), validate=True)
            ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
            tag = base64.b64decode(str(envelope["tag"]), validate=True)
            cipher = AES.new(self._read_key(), AES.MODE_GCM, nonce=nonce, mac_len=16)
            cipher.update(_AAD)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            payload = json.loads(plaintext.decode("utf-8"))
        except RuntimeSecretError:
            raise
        except Exception as exc:
            raise RuntimeSecretError("Encrypted chain configuration could not be verified") from exc
        return ChainSecretBundle.from_payload(payload)

    def _read_bundle(self, path: Path) -> ChainSecretBundle:
        try:
            if not path.is_file():
                raise RuntimeSecretError("Chain configuration generation was not found")
            return self._decrypt(path.read_bytes())
        except RuntimeSecretError:
            raise
        except OSError as exc:
            raise RuntimeSecretError("Encrypted chain configuration is unavailable") from exc

    def _atomic_write(self, path: Path, value: bytes) -> None:
        self._ensure_root()
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_bytes(value)
            try:
                temp.chmod(0o600)
            except OSError:
                pass
            os.replace(temp, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise RuntimeSecretError("Encrypted chain configuration could not be saved") from exc
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def pending_path(self, generation: str) -> Path:
        if not _GENERATION_RE.fullmatch(generation):
            raise RuntimeSecretError("Invalid chain configuration generation")
        return self.root / f"pending-{generation}.enc"

    def stage(self, bundle: ChainSecretBundle) -> None:
        bundle.validate()
        self._atomic_write(self.pending_path(bundle.generation), self._encrypt(bundle))

    def load_pending(self, generation: str) -> ChainSecretBundle:
        bundle = self._read_bundle(self.pending_path(generation))
        if bundle.generation != generation:
            raise RuntimeSecretError("Chain configuration generation mismatch")
        return bundle

    def load_active(self) -> ChainSecretBundle | None:
        if not self.active_path.is_file():
            return None
        return self._read_bundle(self.active_path)

    def activate(self, generation: str) -> ChainSecretBundle:
        pending = self.pending_path(generation)
        bundle = self._read_bundle(pending)
        if bundle.generation != generation:
            raise RuntimeSecretError("Chain configuration generation mismatch")
        self._ensure_root()
        if self.active_path.is_file():
            self._atomic_write(self.previous_path, self.active_path.read_bytes())
        try:
            os.replace(pending, self.active_path)
            self.active_path.chmod(0o600)
        except OSError as exc:
            raise RuntimeSecretError("Chain configuration could not be activated") from exc
        return bundle

    def rollback(self) -> bool:
        if not self.previous_path.is_file():
            return False
        previous = self._read_bundle(self.previous_path)
        self._atomic_write(self.active_path, self.previous_path.read_bytes())
        return bool(previous.generation)

    def quarantine_active(self) -> Path | None:
        if not self.active_path.is_file():
            return None
        self._ensure_root()
        failed = self.root / f"failed-{int(time.time())}-{uuid.uuid4().hex[:8]}.enc"
        try:
            shutil.move(str(self.active_path), str(failed))
            failed.chmod(0o600)
        except OSError as exc:
            raise RuntimeSecretError("Failed chain configuration could not be quarantined") from exc
        return failed

    def prune_pending(self, *, keep: int = 3) -> None:
        try:
            paths = sorted(
                self.root.glob("pending-*.enc"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in paths[max(0, keep) :]:
            try:
                path.unlink()
            except OSError:
                pass
