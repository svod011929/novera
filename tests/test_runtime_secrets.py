from __future__ import annotations

import base64
import secrets

import pytest

from delta_backend.runtime_secrets import (
    ChainSecretBundle,
    RuntimeSecretError,
    RuntimeSecretStore,
)


SEED_ONE = "alpha beta gamma delta echo foxtrot golf hotel india juliet kilo lima"
SEED_TWO = "mango nectar olive piano quartz river solar tango unity violet willow xray"


def _store(tmp_path) -> RuntimeSecretStore:
    key = tmp_path / "runtime_config_key.txt"
    key.write_text(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
    return RuntimeSecretStore(tmp_path / "runtime_secrets", key)


def _bundle(*, seed: str, block: int) -> ChainSecretBundle:
    return ChainSecretBundle.create(
        mode="production",
        chain_id=56,
        rpc_url="https://rpc.example.test/private-key",
        wss_url="wss://wss.example.test/private-key",
        seed_phrase=seed,
        token_contract="0x55d398326f99059fF775485246999027B3197955",
        treasury_address="0x00000000000000000000000000000000000000Aa",
        scan_start_block=block,
    )


def test_runtime_secret_bundle_is_encrypted_and_round_trips(tmp_path) -> None:
    store = _store(tmp_path)
    bundle = _bundle(seed=SEED_ONE, block=100)

    store.stage(bundle)
    encrypted = store.pending_path(bundle.generation).read_bytes()
    assert SEED_ONE.encode() not in encrypted
    assert b"private-key" not in encrypted
    assert store.load_pending(bundle.generation) == bundle

    activated = store.activate(bundle.generation)
    assert activated == bundle
    assert store.load_active() == bundle
    assert not store.pending_path(bundle.generation).exists()


def test_runtime_secret_activation_keeps_rollback_generation(tmp_path) -> None:
    store = _store(tmp_path)
    first = _bundle(seed=SEED_ONE, block=100)
    second = _bundle(seed=SEED_TWO, block=200)
    store.stage(first)
    store.activate(first.generation)
    store.stage(second)
    store.activate(second.generation)

    assert store.load_active() == second
    assert store.rollback() is True
    assert store.load_active() == first


def test_runtime_secret_tampering_fails_without_secret_echo(tmp_path) -> None:
    store = _store(tmp_path)
    bundle = _bundle(seed=SEED_ONE, block=100)
    store.stage(bundle)
    path = store.pending_path(bundle.generation)
    value = bytearray(path.read_bytes())
    value[len(value) // 2] ^= 1
    path.write_bytes(value)

    with pytest.raises(RuntimeSecretError) as caught:
        store.load_pending(bundle.generation)
    assert SEED_ONE not in str(caught.value)
    assert "private-key" not in str(caught.value)
