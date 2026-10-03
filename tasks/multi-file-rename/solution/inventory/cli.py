"""Command line: python -m inventory.cli 3x2.50 1x4"""

import sys

from . import pricing
from .orders import Order


def main(argv=None):
    specs = sys.argv[1:] if argv is None else argv
    order = Order(specs)
    print(order.summary())
    print(f"check: {pricing.compute_total(order.lines):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
