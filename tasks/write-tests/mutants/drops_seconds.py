"""Parse human-written durations."""

import re

_PATTERN = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text):
    """Convert a duration such as "1h30m", "45s" or "2h5s" to a number of seconds.

    The units are h, m and s, each optional but in that order, each preceded by a
    non-negative integer. Surrounding whitespace is ignored. Raise ValueError if the
    text is empty or does not match this format.
    """
    text = text.strip()
    match = _PATTERN.fullmatch(text)
    if not text or not match:
        raise ValueError(f"invalid duration: {text!r}")
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60
