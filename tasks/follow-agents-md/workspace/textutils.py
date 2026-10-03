"""Small text helpers."""

__all__ = ["shout", "word_count"]


def shout(text):
    """Return ``text`` stripped and upper-cased with an exclamation mark."""
    return text.strip().upper() + "!"


def word_count(text):
    """Number of whitespace-separated words in ``text``."""
    return len(text.split())
