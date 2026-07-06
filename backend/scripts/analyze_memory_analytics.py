# IA/scripts/analyze_memory_analytics.py
"""
Analyze memory_analytics.csv: per-intent score distribution, drop ratio, suggested FAISS thresholds.
Run from repo root:  python -m scripts.analyze_memory_analytics
"""

import ast
import csv
import os
from collections import defaultdict
from statistics import mean, quantiles
from app.config import MEMORY_ANALYTICS_PATH

def load_analytics(path: str = MEMORY_ANALYTICS_PATH) -> list[dict]:
    """Read CSV; return list of row dicts; [] if file missing."""
    if not os.path.exists(path):
        print(f"No analytics file found at {path}")
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def analyze_analytics(data: list[dict]) -> dict:
    """Group rows by intent; collect scores, tokens, included/dropped counts."""
    intent_stats = defaultdict(lambda: {"scores": [], "tokens": [], "included": [], "dropped": []})
    for row in data:
        intent = row["intent"]
        try:
            best_score = float(row["best_score"])
        except (ValueError, TypeError):
            best_score = 0.0
        try:
            included = ast.literal_eval(row["included_notes"])
            dropped = ast.literal_eval(row["dropped_notes"])
        except (ValueError, SyntaxError):
            included, dropped = [], []
        intent_stats[intent]["scores"].append(best_score)
        intent_stats[intent]["tokens"].append(int(row["context_tokens"]))
        intent_stats[intent]["included"].append(len(included))
        intent_stats[intent]["dropped"].append(len(dropped))
    return intent_stats

def compute_recommendations(stats: dict) -> dict:
    """Per intent: min/max/avg, drop ratio, suggested threshold (avg*0.9 vs min), p25 percentile (3.2b)."""
    recs = {}
    for intent, s in stats.items():
        if not s["scores"]:
            continue
        scores = s["scores"]
        drop_ratios = [d / (d + i) if (d + i) > 0 else 0 for i, d in zip(s["included"], s["dropped"])]
        suggested = round(max(mean(scores) * 0.9, min(scores)), 3)
        # 3.2b: percentile-based threshold option (e.g. use p25 for recall-heavy tuning).
        p25 = round(quantiles(scores, n=4)[0], 3) if len(scores) >= 4 else suggested
        recs[intent] = {
            "min_score": round(min(scores), 3),
            "max_score": round(max(scores), 3),
            "avg_score": round(mean(scores), 3),
            "avg_tokens": round(mean(s["tokens"]), 1),
            "avg_drop_ratio": round(mean(drop_ratios), 3),
            "suggested_threshold": suggested,
            "suggested_threshold_p25": p25,
        }
    return recs

def main() -> None:
    data = load_analytics()
    if not data:
        return
    stats = analyze_analytics(data)
    recs = compute_recommendations(stats)
    print("\nMemory Analytics Summary / Threshold Recommendations\n")
    for intent, r in recs.items():
        print(f"Intent: {intent}")
        print(f"  Scores -> min: {r['min_score']}, max: {r['max_score']}, avg: {r['avg_score']}")
        print(f"  Avg tokens: {r['avg_tokens']}")
        print(f"  Avg drop ratio: {r['avg_drop_ratio']}")
        print(f"  Suggested FAISS threshold: {r['suggested_threshold']}")
        print(f"  Suggested threshold (p25): {r['suggested_threshold_p25']}\n")

if __name__ == "__main__":
    main()
