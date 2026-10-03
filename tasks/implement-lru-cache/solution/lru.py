"""A least-recently-used cache."""

from collections import OrderedDict


class LRUCache:
    """Fixed-capacity mapping that evicts the least recently used key when full.

    "Used" means read with ``get`` (a hit) or written with ``put``. ``len()`` and the
    ``in`` operator do not count as uses.
    """

    def __init__(self, capacity):
        """Create an empty cache. Raise ValueError unless ``capacity`` is an int >= 1."""
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        self.capacity = capacity
        self._data = OrderedDict()

    def get(self, key, default=None):
        """Return the value for ``key`` and mark it most recently used, else ``default``."""
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key, value):
        """Insert or update ``key`` and mark it most recently used.

        If the cache then holds more than ``capacity`` keys, evict the least recently
        used key and return it. Otherwise return None.
        """
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            evicted, _ = self._data.popitem(last=False)
            return evicted
        return None

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data
