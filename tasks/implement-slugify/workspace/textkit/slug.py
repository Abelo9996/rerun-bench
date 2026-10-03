"""URL slug generation."""


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
    raise NotImplementedError
