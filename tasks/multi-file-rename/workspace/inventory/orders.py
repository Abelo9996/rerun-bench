"""Order objects."""

from .pricing import calc_ttl, parse_line


class Order:
    def __init__(self, specs):
        self.lines = [parse_line(s) for s in specs]

    def total(self):
        return calc_ttl(self.lines)

    def summary(self):
        return f"{len(self.lines)} lines, total {calc_ttl(self.lines):.2f}"
