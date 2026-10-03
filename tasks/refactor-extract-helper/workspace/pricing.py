"""Price calculations for the storefront."""

MAX_DISCOUNT = 90


def member_price(price, percent):
    """Price after a member discount of ``percent`` (clamped to 0..MAX_DISCOUNT)."""
    if percent < 0:
        percent = 0
    if percent > MAX_DISCOUNT:
        percent = MAX_DISCOUNT
    return round(price * (100 - percent) / 100, 2)


def sale_price(price, percent, floor=1.0):
    """Sale price, never below ``floor``."""
    if percent < 0:
        percent = 0
    if percent > MAX_DISCOUNT:
        percent = MAX_DISCOUNT
    return max(floor, round(price * (100 - percent) / 100, 2))


def bulk_price(unit_price, quantity, percent):
    """Total for ``quantity`` units; the discount only applies from 10 units up."""
    if percent < 0:
        percent = 0
    if percent > MAX_DISCOUNT:
        percent = MAX_DISCOUNT
    if quantity < 10:
        percent = 0
    return round(unit_price * quantity * (100 - percent) / 100, 2)
