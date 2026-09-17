# IA/backend/app/config.py

import os

# auth: JWT for login (no API secret in UI). Set JWT_SECRET in .env (do not commit).
JWT_SECRET = (os.getenv("JWT_SECRET") or os.getenv("API_SECRET", "change-me-in-production")).strip()
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS = int(os.getenv("JWT_EXP_DAYS", "7"))

# AI provider
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "groq")
# Groq: primary (free, no card). Override in .env: GROQ_ENDPOINT, GROQ_MODEL.
GROQ_ENDPOINT = os.getenv("GROQ_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# DeepSeek: alternative (project.md free-tier). Set MODEL_PROVIDER=deepseek + AI_KEY.
DEEPSEEK_ENDPOINT = os.getenv("DEEPSEEK_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat")
# Ollama: local, no key. Run: ollama run llama2
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama2")
AI_MODE = os.getenv("AI_MODE", "single")  # single | ensemble | judge (project.md Phase 4)
# Comma-separated providers for ensemble/judge (e.g. groq,ollama). Default groq only (single effective).
AI_ENSEMBLE_PROVIDERS = [p.strip() for p in os.getenv("AI_ENSEMBLE_PROVIDERS", "groq").split(",") if p.strip()]

AI_KEY = os.getenv("AI_KEY", "")

# Internal product currency. These are AI Credits, not provider tokens.
AI_CREDIT_INITIAL_BALANCE = int(os.getenv("AI_CREDIT_INITIAL_BALANCE", "10"))
AI_ASK_CREDIT_COST = int(os.getenv("AI_ASK_CREDIT_COST", "1"))
REWARDED_AD_CREDIT_AMOUNT = int(os.getenv("REWARDED_AD_CREDIT_AMOUNT", "10"))
AI_UNLIMITED_ROLE = os.getenv("AI_UNLIMITED_ROLE", "admin").strip()

# context & FAISS
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", 500))
FAISS_LOG_SCORES = os.getenv("FAISS_LOG_SCORES", "true").lower() == "true"
FAISS_SCORE_LOG_PATH = os.getenv("FAISS_SCORE_LOG_PATH", "data/faiss_scores.log")
# Thresholds from scripts/analyze_memory_analytics; override in .env (docs/project.md FAISS tuning).
FAISS_THRESHOLD_LOOKUP = float(os.getenv("FAISS_THRESHOLD_LOOKUP", 0.54))
FAISS_THRESHOLD_EXPLORATORY = float(os.getenv("FAISS_THRESHOLD_EXPLORATORY", 0.649))
MAX_FAISS_RESULTS = int(os.getenv("MAX_FAISS_RESULTS", 10))
LOG_DROPPED_NOTES = os.getenv("LOG_DROPPED_NOTES", "true").lower() == "true"

# intent cache
INTENT_CACHE_MAX_SIZE = int(os.getenv("INTENT_CACHE_MAX_SIZE", 1000))
INTENT_CACHE_TTL = int(os.getenv("INTENT_CACHE_TTL", 300))
INTENT_CACHE_LOG_HITS = os.getenv("INTENT_CACHE_LOG_HITS", "true").lower() == "true"

# memory analytics (per-query logging)
MEMORY_ANALYTICS_ENABLED = os.getenv("MEMORY_ANALYTICS_ENABLED", "false").lower() == "true"
MEMORY_ANALYTICS_FORMAT = os.getenv("MEMORY_ANALYTICS_FORMAT", "csv")
MEMORY_ANALYTICS_PATH = os.getenv("MEMORY_ANALYTICS_PATH", "data/memory_analytics.csv")

# CORS: comma-separated origins (e.g. Vite dev). Empty = no CORS. Default allows localhost:5174.
CORS_ORIGINS = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5174,http://127.0.0.1:5174").split(",") if o.strip()]
