"""
Code inspired by https://www.geeksforgeeks.org/lru-cache-in-python-using-ordereddict/
"""

from collections import OrderedDict
from typing import Any


class LRUCache:
    # initialising capacity
    def __init__(self, capacity: int):
        self._cache = OrderedDict()
        self._capacity = capacity

    # we return the value of the key
    # And also move the key to the end
    # to show that it was recently used.
    # raise error if key does not exist
    def get(self, key: Any) -> Any:
        self._cache.move_to_end(key)
        return self._cache[key]

    # first, we add / update the key by conventional methods.
    # And also move the key to the end to show that it was recently used.
    # But here we will also check whether the length of our
    # ordered dictionary has exceeded our capacity,
    # If so we remove the first key (least recently used)
    def put(self, key: Any, value: Any) -> Any:
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self._capacity:
            self._cache.popitem(last=False)

    def clear(self) -> Any:
        self._cache.clear()

    def keyExist(self, key: Any) -> bool:
        return key in self._cache

    def length(self):
        return len(self._cache)

    def capcacity(self):
        return self._capacity


class WidgetLRUCache(LRUCache):
    """Apply widget.deleteLater() method to the widget at deletion"""

    def put(self, key: Any, value: Any) -> Any:
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self._capacity:
            _, v = self._cache.popitem(last=False)
            v.deleteLater()

    def clear(self) -> Any:
        for v in self._cache.values():
            v.deleteLater()
        self._cache.clear()
