# IA/backend/scripts/analyze_ai_diagnostics.py
"""Summarize stored AI diagnostic events for operator review."""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.diagnostics import manager


def main() -> int:
    events = manager.list_events_admin(limit=manager.MAX_ADMIN_LIMIT)
    if not events:
        print("No diagnostic events found.")
        return 0

    by_code = Counter(event.get("code") for event in events)
    by_kind = Counter(event.get("kind") for event in events)
    by_feature = Counter(event.get("feature") for event in events)
    by_reason = Counter(
        event.get("feedback_reason")
        for event in events
        if event.get("kind") == "user_report"
    )

    print(f"events={len(events)}")
    print("by_kind:", dict(by_kind))
    print("by_feature:", dict(by_feature))
    print("by_code:", dict(by_code))
    if by_reason:
        print("feedback_reasons:", dict(by_reason))

    print("\nrecent_events:")
    for event in events[:20]:
        print(json.dumps({
            "timestamp": event.get("timestamp"),
            "kind": event.get("kind"),
            "code": event.get("code"),
            "category": event.get("category"),
            "feature": event.get("feature"),
            "fallback": event.get("fallback"),
            "error_type": event.get("error_type"),
            "provider": event.get("provider"),
            "model": event.get("model"),
            "operation_id": event.get("operation_id"),
            "feedback_reason": event.get("feedback_reason"),
            "user_key_prefix": event.get("user_key_prefix"),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
