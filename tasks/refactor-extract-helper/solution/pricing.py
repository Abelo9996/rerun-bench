"""Price calculations for the storefront."""

MAX_DISCOUNT = 90


def clamp_percent(percent):
    """Clamp a discount percentage to 0..MAX_DISCOUNT."""
    if percent < 0:
        return 0
    if percent > MAX_DISCOUNT:
        return MAX_DISCOUNT
    return percent


def member_price(price, percent):
    """Price after a member discount of ``percent`` (clamped to 0..MAX_DISCOUNT)."""
    percent = clamp_percent(percent)
    return round(price * (100 - percent) / 100, 2)


def sale_price(price, percent, floor=1.0):
    """Sale price, never below ``floor``."""
    percent = clamp_percent(percent)
    return max(floor, round(price * (100 - percent) / 100, 2))


def bulk_price(unit_price, quantity, percent):
    """Total for ``quantity`` units; the discount only applies from 10 units up."""
    percent = clamp_percent(percent)
    if quantity < 10:
        percent = 0
    return round(unit_price * quantity * (100 - percent) / 100, 2)
