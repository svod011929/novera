from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Plan:
    id: int
    code: str
    days: int
    profit_bps: int
    referral_bps: int
    min_minor: int
    max_minor: int
    enabled: bool


@dataclass(slots=True, frozen=True)
class TransferEvent:
    chain_id: int
    tx_hash: str
    log_index: int
    block_number: int
    from_address: str
    to_address: str
    amount_atomic: int
    amount_minor: int


@dataclass(slots=True, frozen=True)
class SignedTransfer:
    tx_hash: str
    raw_transaction: str
    nonce: int

