"""Small descriptive statistics helpers."""


def mean(xs):
    """Arithmetic mean. Raises ValueError on empty input."""
    if not xs:
        raise ValueError("mean of empty sequence")
    return sum(xs) / len(xs)


def median(xs):
    """Median of a sequence of numbers. Raises ValueError on empty input.

    For an even number of values the median is the mean of the two middle values.
    The input sequence is not modified.
    """
    if not xs:
        raise ValueError("median of empty sequence")
    s = sorted(xs)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
