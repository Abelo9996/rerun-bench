"""Line-item parsing and totals."""


def parse_line(spec):
    """Parse "<qty>x<unit price>" into (qty, unit_price)."""
    qty, price = spec.lower().split("x", 1)
    return int(qty), float(price)


def calc_ttl(lines):
    """Total price for a list of (qty, unit_price) tuples, rounded to cents."""
    return round(sum(q * p for q, p in lines), 2)
