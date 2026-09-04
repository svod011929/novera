from decimal import Decimal, InvalidOperation

DISPLAY_DECIMALS = 6
MINOR_FACTOR = 10**DISPLAY_DECIMALS
MAX_MINOR = 9_000_000_000_000_000_000


class AmountError(ValueError):
    pass


def usdt_to_minor(value: str | Decimal | int) -> int:
    try:
        amount = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise AmountError("invalid decimal amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise AmountError("amount must be positive")
    scaled = amount * MINOR_FACTOR
    if scaled != scaled.to_integral_value():
        raise AmountError(f"maximum precision is {DISPLAY_DECIMALS} decimals")
    minor = int(scaled)
    if minor > MAX_MINOR:
        raise AmountError("amount is too large")
    return minor


def minor_to_text(value: int, *, trim: bool = True) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole, fraction = divmod(value, MINOR_FACTOR)
    if not fraction:
        return f"{sign}{whole}"
    suffix = f"{fraction:0{DISPLAY_DECIMALS}d}"
    if trim:
        suffix = suffix.rstrip("0")
    return f"{sign}{whole}.{suffix}"


def calculate_bps(value_minor: int, basis_points: int) -> int:
    if value_minor < 0 or basis_points < 0:
        raise AmountError("negative value is not allowed")
    return value_minor * basis_points // 10_000


def minor_to_atomic(value_minor: int, token_decimals: int) -> int:
    if value_minor <= 0 or value_minor > MAX_MINOR:
        raise AmountError("amount is outside the accounting range")
    if token_decimals < DISPLAY_DECIMALS:
        divisor = 10 ** (DISPLAY_DECIMALS - token_decimals)
        if value_minor % divisor:
            raise AmountError("amount cannot be represented by token decimals")
        return value_minor // divisor
    return value_minor * 10 ** (token_decimals - DISPLAY_DECIMALS)


def atomic_to_minor(value_atomic: int, token_decimals: int) -> int:
    if token_decimals < DISPLAY_DECIMALS:
        minor = value_atomic * 10 ** (DISPLAY_DECIMALS - token_decimals)
    else:
        divisor = 10 ** (token_decimals - DISPLAY_DECIMALS)
        if value_atomic % divisor:
            raise AmountError("transfer has more precision than the accounting ledger")
        minor = value_atomic // divisor
    if minor <= 0 or minor > MAX_MINOR:
        raise AmountError("transfer is outside the accounting range")
    return minor


def bps_to_percent_text(basis_points: int) -> str:
    whole, fraction = divmod(basis_points, 100)
    return str(whole) if not fraction else f"{whole}.{fraction:02d}".rstrip("0")


def percent_to_bps(value: str | Decimal) -> int:
    try:
        percent = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise AmountError("invalid percentage") from exc
    if not percent.is_finite() or percent < 0:
        raise AmountError("percentage must not be negative")
    basis_points = percent * 100
    if basis_points != basis_points.to_integral_value():
        raise AmountError("maximum percentage precision is 0.01")
    return int(basis_points)
