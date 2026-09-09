"""Near-miss heuristics for unmatched treasury transfers vs an invoice."""

from delta_backend.amounts import MINOR_FACTOR

MISMATCH_LOOKBACK_SECONDS = 300
MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS = 7200
MISMATCH_AMOUNT_TOLERANCE_MINOR = 1 * MINOR_FACTOR  # 1.00 USDT in minor units


def _in_time_window(invoice: dict, created_at: int) -> bool:
    start = int(invoice["created_at"]) - MISMATCH_LOOKBACK_SECONDS
    end = int(invoice["expires_at"]) + MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS
    return start <= int(created_at) <= end


def _amount_matches(invoice: dict, amount_minor: int) -> bool:
    amount_minor = int(amount_minor)
    if amount_minor == int(invoice["base_minor"]):
        return True
    return abs(amount_minor - int(invoice["exact_minor"])) <= MISMATCH_AMOUNT_TOLERANCE_MINOR


def select_mismatch_candidate(
    invoice: dict, candidates: list[dict]
) -> dict | None:
    usable: list[dict] = []
    for row in candidates:
        if int(row.get("matched") or 0) != 0:
            continue
        if not _in_time_window(invoice, int(row["created_at"])):
            continue
        if not _amount_matches(invoice, int(row["amount_minor"])):
            continue
        usable.append(row)
    if not usable:
        return None
    created = int(invoice["created_at"])
    exact = int(invoice["exact_minor"])
    usable.sort(
        key=lambda r: (
            abs(int(r["created_at"]) - created),
            abs(int(r["amount_minor"]) - exact),
            int(r["id"]),
        )
    )
    return usable[0]
