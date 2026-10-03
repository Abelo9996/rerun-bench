"""URL slug generation."""

import re
import unicodedata


def slugify(text: str, max_length: int = 50) -> str:
    """Turn arbitrary text into a URL slug.

    Rules, applied in this order:

    1. Normalize with Unicode NFKD and drop every character that is not ASCII
       (so "Cafe" with an accent becomes "Cafe").
    2. Lowercase.
    3. Replace every run of characters that are not ASCII letters or digits with a
       single hyphen.
    4. Strip leading and trailing hyphens.
    5. If the result is longer than ``max_length``, cut it to ``max_length`` characters
       and strip any trailing hyphen left by the cut.
    6. If the result is empty, return "n-a".

    ``max_length`` must be at least 1; otherwise raise ValueError.
    """
    if max_length < 1:
        raise ValueError("max_length must be >= 1")
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s or "n-a"
