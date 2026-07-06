# IA/backend/app/memory/summarizer.py
"""First max_sentences sentences; else full text. Replace with LLM later if needed."""

def summarize_text(text: str, max_sentences: int = 3):
    sentences = text.split(". ")
    if len(sentences) <= max_sentences:
        return text
    return ". ".join(sentences[:max_sentences]) + "..."
