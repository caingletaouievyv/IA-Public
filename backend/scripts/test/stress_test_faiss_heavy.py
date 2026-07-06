# IA/scripts/test/stress_test_faiss_heavy.py

import os
import requests
import datetime
import random
import time
from dotenv import load_dotenv

BASE_URL = "http://127.0.0.1:5000"
NUM_NOTES = 500      # total notes to insert
QUERY_COUNT = 200    # total queries to test retrieval

load_dotenv()
API_SECRET = os.getenv("API_SECRET")

HEADERS = {
    "Authorization": f"Bearer {API_SECRET}",
    "Content-Type": "application/json"
}

# ---------- Notes ----------
def create_note(i):
    """Create a unique note for FAISS testing."""
    now = datetime.datetime.utcnow().isoformat()
    
    # Distinct titles and content
    title = f"Stress Note {i}"
    category = "StressTest" if i % 5 else "DevNotes"
    tags = ["faiss", "stress", "memory"]
    
    if i % 10 == 0:
        # Introduce a semantic/unique note every 10th
        title = f"FAISS Special Note {i}"
        tags.append("special")
    
    # Repeat content slightly for chunking test
    body = (
        f"{title}: This note exists to validate FAISS vector retrieval, "
        f"persistent memory, deduplication, and token estimation consistency. "
        "Extra filler text to increase token load. " * 3
    )
    
    return {
        "id": f"note-{i:05d}",
        "title": title,
        "content": body,
        "category": category,
        "tags": tags,
        "created_at": now,
        "updated_at": now
    }

def add_notes():
    print("\n--- Adding notes ---")
    for i in range(1, NUM_NOTES + 1):
        r = requests.post(f"{BASE_URL}/notes", json=create_note(i), headers=HEADERS)
        print(f"[{i}/{NUM_NOTES}] {'OK' if r.ok else 'FAIL'}")
        time.sleep(0.005)  # slight delay to avoid overwhelming the server

# ---------- Queries ----------
QUERY_POOL = [
    "stress test note number {n}",
    "find stress note {n}",
    "notes mentioning FAISS",
    "notes about memory retrieval",
    "FAISS special note",
    "persistent memory cache",
    "vector indexing",
    "semantic retrieval",
    "deduplication test"
]

def query_ai(q):
    """Query AI endpoint and debug context."""
    payload = {"question": q}
    
    # Main AI response
    r = requests.post(f"{BASE_URL}/ai/ask", json=payload, headers=HEADERS)
    est_tokens = r.json().get("tokens_estimated", 0) if r.ok else 0
    
    # Debug: check retrieved context
    rc = requests.post(f"{BASE_URL}/ai/debug/context", json=payload, headers=HEADERS)
    ctx = rc.json().get("context", "") if rc.ok else ""
    
    retrieved = len(ctx.splitlines())
    ctx_tokens = len(ctx.split())
    fallback = retrieved == 0

    return fallback, retrieved, ctx_tokens, est_tokens

# ---------- Run ----------
def run():
    add_notes()

    print("\n--- Querying ---")
    stats = {
        "fallbacks": 0,
        "retrieved": 0,
        "ctx_tokens": 0,
        "est_tokens": 0,
        "dropped_notes": 0,
        "best_scores": [],
        "lookup_queries": 0,
        "exploratory_queries": 0
    }

    for i in range(QUERY_COUNT):
        n = random.randint(1, NUM_NOTES)
        q = random.choice(QUERY_POOL).format(n=n)

        fb, r, ct, et = query_ai(q)
        
        # Debug context call for extra info
        rc = requests.post(f"{BASE_URL}/ai/debug/context", json={"question": q}, headers=HEADERS)
        data = rc.json() if rc.ok else {}
        dropped = len(data.get("dropped_notes", []))
        best_score = data.get("best_faiss_score") or 0
        intent = "lookup" if any(k in q.lower() for k in ["find", "stress"]) else "exploratory"

        stats["fallbacks"] += fb
        stats["retrieved"] += r
        stats["ctx_tokens"] += ct
        stats["est_tokens"] += et
        stats["dropped_notes"] += dropped
        stats["best_scores"].append(best_score)
        if intent == "lookup":
            stats["lookup_queries"] += 1
        else:
            stats["exploratory_queries"] += 1

        if i % 20 == 0:
            print(f"[{i}/{QUERY_COUNT}] Q='{q}' | retrieved={r}, dropped={dropped}, ctx_tokens={ct}, est_tokens={et}, best_score={best_score:.3f}")

    avg_best_score = sum(stats["best_scores"])/len(stats["best_scores"]) if stats["best_scores"] else 0

    print("\n=== FAISS HEAVY STRESS TEST SUMMARY ===")
    print(f"Total queries: {QUERY_COUNT}")
    print(f"Fallbacks (no context): {stats['fallbacks']}")
    print(f"Avg notes retrieved/query: {stats['retrieved']/QUERY_COUNT:.2f}")
    print(f"Avg dropped notes/query: {stats['dropped_notes']/QUERY_COUNT:.2f}")
    print(f"Avg context tokens/query: {stats['ctx_tokens']/QUERY_COUNT:.1f}")
    print(f"Avg estimated tokens/query: {stats['est_tokens']/QUERY_COUNT:.1f}")
    print(f"Avg best FAISS score/query: {avg_best_score:.3f}")
    print(f"Lookup vs Exploratory queries: {stats['lookup_queries']} / {stats['exploratory_queries']}")

if __name__ == "__main__":
    run()
