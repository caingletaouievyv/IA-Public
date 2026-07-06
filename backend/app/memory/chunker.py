# IA/backend/app/memory/chunker.py

def chunk_text(text: str, chunk_size=120, overlap=30):
    """Split into overlapping word windows; chunk_size words, step chunk_size - overlap."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks
