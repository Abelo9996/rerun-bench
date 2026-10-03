"""A least-recently-used cache."""


class LRUCache:
    """Fixed-capacity mapping that evicts the least recently used key when full.

    "Used" means read with ``get`` (a hit) or written with ``put``. ``len()`` and the
    ``in`` operator do not count as uses.
    """

    def __init__(self, capacity):
        """Create an empty cache. Raise ValueError unless ``capacity`` is an int >= 1."""
        raise NotImplementedError

    def get(self, key, default=None):
        """Return the value for ``key`` and mark it most recently used, else ``default``."""
        raise NotImplementedError

    def put(self, key, value):
        """Insert or update ``key`` and mark it most recently used.

        If the cache then holds more than ``capacity`` keys, evict the least recently
        used key and return it. Otherwise return None.
        """
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError

    def __contains__(self, key):
        raise NotImplementedError
