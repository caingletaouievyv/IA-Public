# IA/backend/app/memory/utils.py

import tiktoken

def estimate_tokens(text: str, model_name: str = "gpt-3.5-turbo"):
    """Token count via tiktoken; fallback cl100k_base if model unknown."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
