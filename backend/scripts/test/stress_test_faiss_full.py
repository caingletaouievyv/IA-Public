# IA/scripts/test/stress_test_faiss_full.py
# Stress test: register/login, add notes, query /ai/ask and /ai/debug/context. Auth via JWT.

import os
import requests
import datetime
import random
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
NUM_NOTES = 100
QUERY_COUNT = 40
try:
    from scripts.test.auth_helper import get_token
except ImportError:
    from auth_helper import get_token


def get_headers():
    token = get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# --- Note creation ---
def create_note(i):
    now = datetime.datetime.now(datetime.UTC).isoformat()
    return {
        "title": f"Stress Test Note {i}",
        "content": f"This is stress test note number {i}. FAISS retrieval check.",
        "category": "DevNotes",
        "tags": ["test", "memory"],
        "id": f"note-{i:03d}",
        "created_at": now,
        "updated_at": now
    }


def add_notes():
    print("Adding notes...")
    headers = get_headers()
    for i in range(1, NUM_NOTES + 1):
        note = create_note(i)
        resp = requests.post(f"{BASE_URL}/notes", json=note, headers=headers)
        print(f"[{i}] {'OK' if resp.ok else 'FAIL'}")
        time.sleep(0.01)


# --- Query AI + estimate tokens ---
UNRELATED_QUERIES = [
    "tell me a joke", "meaning of life", "how to cook pasta?",
    "random question", "weather today", "define serendipity",
    "latest news", "fun fact about space"
]


def query_ai(question):
    payload = {"question": question}
    headers = get_headers()

    resp = requests.post(f"{BASE_URL}/ai/ask", json=payload, headers=headers)
    answer = resp.json().get("answer", "") if resp.ok else f"ERROR: {resp.text}"

    resp_ctx = requests.post(f"{BASE_URL}/ai/debug/context", json=payload, headers=headers)
    context = resp_ctx.json().get("context", "") if resp_ctx.ok else ""
    context_tokens = resp_ctx.json().get("context_tokens", len(context.split()))

    resp_est = requests.post(f"{BASE_URL}/ai/estimate_tokens", json=payload, headers=headers)
    est_tokens = resp_est.json().get("estimated_tokens", 0) if resp_est.ok else 0

    fallback = len(context.strip()) == 0
    retrieved_count = len(context.splitlines())

    return fallback, retrieved_count, context_tokens, est_tokens, answer


def run_full_test():
    add_notes()

    queries = []
    for _ in range(QUERY_COUNT):
        base = random.randint(1, NUM_NOTES - 5)
        queries.extend([
            f"stress test note number {base}",
            f"stress test note number {base+1}",
            f"stress test note number {base+2}",
            random.choice(UNRELATED_QUERIES)
        ])

    fallback_count = 0
    total_retrieved = 0
    total_context_tokens = 0
    total_est_tokens = 0

    print("\n--- Querying ---\n")
    for q in queries:
        fallback, retrieved_count, ctx_tokens, est_tokens, answer = query_ai(q)
        fallback_count += int(fallback)
        total_retrieved += retrieved_count
        total_context_tokens += ctx_tokens
        total_est_tokens += est_tokens

        print(f"Q: {q}")
        print(f"Fallback: {fallback}, Retrieved: {retrieved_count}, Context tokens: {ctx_tokens}, Est tokens: {est_tokens}")
        print(f"Answer: {answer[:120]}{'...' if len(answer) > 120 else ''}\n")
        time.sleep(0.05)

    total_queries = len(queries)
    print("\n=== FAISS + AI Full Stress Test Summary ===")
    print(f"Total queries: {total_queries}")
    print(f"Fallbacks triggered: {fallback_count}")
    print(f"Average notes retrieved/query: {total_retrieved/total_queries:.2f}")
    print(f"Average context tokens/query: {total_context_tokens/total_queries:.1f}")
    print(f"Average estimated tokens/query: {total_est_tokens/total_queries:.1f}")


if __name__ == "__main__":
    run_full_test()
