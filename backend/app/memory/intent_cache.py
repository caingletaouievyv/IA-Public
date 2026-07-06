# IA/backend/app/memory/intent_cache.py
"""LRU cache for build_context results; TTL in seconds; optional hit/miss logging."""

import time
from collections import OrderedDict
import logging
from app.config import INTENT_CACHE_LOG_HITS

logger = logging.getLogger(__name__)

class IntentLRUCache:
    def __init__(self, max_size=1000, ttl=300):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl

    def _is_expired(self, entry):
        return time.time() - entry[1] > self.ttl

    def get(self, key):
        """Return value if hit and not expired; else None. Refresh LRU on hit."""
        if key not in self.cache:
            if INTENT_CACHE_LOG_HITS:
                logger.debug(f"IntentCache MISS: {key}")
            return None
        value, ts = self.cache.pop(key)
        if self._is_expired((value, ts)):
            if INTENT_CACHE_LOG_HITS:
                logger.debug(f"IntentCache EXPIRED: {key}")
            return None
        self.cache[key] = (value, ts)
        if INTENT_CACHE_LOG_HITS:
            logger.debug(f"IntentCache HIT: {key}")
        return value

    def set(self, key, value):
        """Insert or update; evict oldest if at max_size."""
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.max_size:
            evicted = self.cache.popitem(last=False)
            if INTENT_CACHE_LOG_HITS:
                logger.debug(f"IntentCache EVICT: {evicted[0]}")
        self.cache[key] = (value, time.time())
