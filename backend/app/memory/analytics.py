# IA/backend/app/memory/analytics.py
"""Per-query memory analytics: dropped notes, token usage, FAISS scores. Write-only; no-op if disabled."""

import csv
import json
import os
from datetime import datetime
from app.config import MEMORY_ANALYTICS_ENABLED, MEMORY_ANALYTICS_PATH, MEMORY_ANALYTICS_FORMAT

_ANALYTICS_FIELDS = ["timestamp", "query", "intent", "best_score", "context_tokens", "included_notes", "dropped_notes"]

def log_memory_event(*, query: str, intent: str, best_score: float | None, context_tokens: int, included_notes: list[str], dropped_notes: list[str]):
    """Append one record to CSV or JSONL; no-op if MEMORY_ANALYTICS_ENABLED false."""
    if not MEMORY_ANALYTICS_ENABLED:
        return
    record = {"timestamp": datetime.utcnow().isoformat(), "query": query, "intent": intent, "best_score": best_score, "context_tokens": context_tokens, "included_notes": included_notes, "dropped_notes": dropped_notes}
    os.makedirs(os.path.dirname(MEMORY_ANALYTICS_PATH), exist_ok=True)
    if MEMORY_ANALYTICS_FORMAT == "csv":
        _write_csv(record)
    else:
        _write_jsonl(record)

def _write_csv(record: dict):
    """Append row; write header if file new."""
    file_exists = os.path.exists(MEMORY_ANALYTICS_PATH)
    with open(MEMORY_ANALYTICS_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_ANALYTICS_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)

def _write_jsonl(record: dict):
    """Append one JSON line."""
    with open(MEMORY_ANALYTICS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
