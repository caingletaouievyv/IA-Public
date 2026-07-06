# IA/scripts/test/test_semantic_retrieval_and_chunked_notes.py 

import os, requests
from dotenv import load_dotenv

load_dotenv()
API_SECRET = os.getenv("API_SECRET")
HEADERS = {"Authorization": f"Bearer {API_SECRET}", "Content-Type": "application/json"}

queries = [
    "find stress note 42",
    "faiss memory",
    "tell me a joke",
    "persistent memory cache",
]

BASE_URL = "http://127.0.0.1:5000"

for q in queries:
    r = requests.post(f"{BASE_URL}/ai/debug/context", json={"question": q}, headers=HEADERS)
    if not r.ok:
        print(f"\nQuestion: {q}\nError fetching context: {r.text}")
        continue

    data = r.json()
    best_score = data.get("best_faiss_score")
    context_lines = data.get("context", "").splitlines()
    dropped_notes = data.get("dropped_notes", [])

    print(f"\nQuestion: {q}")
    print(f"Best FAISS score: {best_score:.3f}" if best_score is not None else "Best FAISS score: None")
    print(f"Context tokens: {data.get('context_tokens', 0)}")
    print(f"Dropped notes: {len(dropped_notes)}")

    print("Context preview (first 3 notes or lines):")
    for line in context_lines[:3]:
        snippet = line[:150] + ("..." if len(line) > 150 else "")
        print(f"- {snippet}")