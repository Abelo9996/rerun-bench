"""Hidden checks for implement-lru-cache."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


try:
    from lru import LRUCache

    for bad in (0, -3, 1.5, "2", None):
        try:
            LRUCache(bad)
        except ValueError:
            continue
        fail(f"LRUCache({bad!r}) should raise ValueError")

    c = LRUCache(2)
    if c.put("a", 1) is not None or c.put("b", 2) is not None:
        fail("put below capacity should return None")
    if c.get("a") != 1:
        fail("get a")
    if c.put("c", 3) != "b":
        fail("expected b evicted after a was read")
    if "b" in c or c.get("b", "miss") != "miss":
        fail("b should be gone")
    if len(c) != 2:
        fail("len should be 2")
    if c.put("a", 10) is not None or c.get("a") != 10:
        fail("updating an existing key should not evict and should store the new value")
    if c.put("d", 4) != "c":
        fail("expected c evicted (a was used more recently)")
    _ = "a" in c
    _ = len(c)
    if c.put("e", 5) != "a":
        fail("`in` and len() must not count as uses")
    if c.get("missing") is not None:
        fail("missing key should return None by default")

    one = LRUCache(1)
    one.put(1, "x")
    if one.put(2, "y") != 1 or one.get(2) != "y" or len(one) != 1:
        fail("capacity-1 behavior")

    big = LRUCache(100)
    for i in range(250):
        big.put(i, i * i)
    if len(big) != 100 or 149 in big or big.get(150) != 22500:
        fail("bulk insert behavior")
except NotImplementedError:
    fail("LRUCache is not implemented")
print("PASS")
