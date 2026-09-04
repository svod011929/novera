from enum import StrEnum


class InvestmentStatus(StrEnum):
    ACTIVE = "active"
    PAYOUT_QUEUED = "payout_queued"
    PAID = "paid"
    FAILED = "failed"


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"


class PayoutStatus(StrEnum):
    QUEUED = "queued"
    SIGNED = "signed"
    BROADCAST = "broadcast"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class PayoutKind(StrEnum):
    INVESTMENT = "investment"
    REFERRAL = "referral"


class ReferralPayoutMode(StrEnum):
    BALANCE = "balance"
    WALLET = "wallet"

