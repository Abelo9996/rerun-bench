"""Order objects."""

from .pricing import compute_total, parse_line


class Order:
    def __init__(self, specs):
        self.lines = [parse_line(s) for s in specs]

    def total(self):
        return compute_total(self.lines)

    def summary(self):
        return f"{len(self.lines)} lines, total {compute_total(self.lines):.2f}"
