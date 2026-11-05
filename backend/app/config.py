# IA/backend/app/config.py

import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() == "true"


# auth: JWT for login (no API secret in UI). Set JWT_SECRET in .env (do not commit).
JWT_SECRET = (os.getenv("JWT_SECRET") or "").strip()
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS = int(os.getenv("JWT_EXP_DAYS", "7"))
APP_ENV = (os.getenv("APP_ENV") or "production").strip().lower()


def database_url() -> str:
    """Return DATABASE_URL from the current environment.

    Read on each call. A value captured at import would stay stale when tests
    or Alembic change the environment later.
    """
    return (os.getenv("DATABASE_URL") or "").strip()

# Local development only: optional Main Admin auto-seed (password read in main_admin; not stored here).
IA_AUTO_SEED_MAIN_ADMIN = _bool_env("IA_AUTO_SEED_MAIN_ADMIN", False)
IA_AUTO_SEED_MAIN_ADMIN_USERNAME = (os.getenv("IA_AUTO_SEED_MAIN_ADMIN_USERNAME") or "").strip()
# Production one-time empty-store bootstrap (credentials read in main_admin; not stored here).
IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN = _bool_env("IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN", False)


def validate_jwt_secret(secret: str | None = None) -> str:
    value = JWT_SECRET if secret is None else secret.strip()
    known_placeholders = {"change-me-in-production", "changeme", "secret", "password", "test-secret"}
    if len(value) < 32 or len(set(value)) < 8 or value.casefold() in known_placeholders:
        raise RuntimeError("JWT_SECRET must be configured with at least 32 characters of non-placeholder secret material.")
    return value

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
AI_CREDIT_INITIAL_BALANCE = int(os.getenv("AI_CREDIT_INITIAL_BALANCE", "100"))
AI_ASK_CREDIT_COST = int(os.getenv("AI_ASK_CREDIT_COST", "1"))
REWARDED_AD_CREDIT_AMOUNT = int(os.getenv("REWARDED_AD_CREDIT_AMOUNT", "10"))
AI_UNLIMITED_ROLE = os.getenv("AI_UNLIMITED_ROLE", "admin").strip()

# AI diagnostics (content-free fallback and feedback records)
DIAGNOSTICS_ENABLED = _bool_env("DIAGNOSTICS_ENABLED", True)
DIAGNOSTICS_MAX_EVENTS_PER_USER = int(os.getenv("DIAGNOSTICS_MAX_EVENTS_PER_USER", "200"))
DIAGNOSTICS_RETENTION_DAYS = int(os.getenv("DIAGNOSTICS_RETENTION_DAYS", "90"))

# context & retrieval
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", 500))
MEMORY_RETRIEVAL = os.getenv("MEMORY_RETRIEVAL", "text").strip().lower()
# Lexical scores are normalized to 0..1 and use thresholds separate from FAISS scores.
TEXT_RETRIEVAL_THRESHOLD_LOOKUP = float(os.getenv("TEXT_RETRIEVAL_THRESHOLD_LOOKUP", 0.20))
TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY = float(os.getenv("TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY", 0.20))
# Thresholds from scripts/analyze_memory_analytics; override in .env (docs/project.md FAISS tuning).
FAISS_THRESHOLD_LOOKUP = float(os.getenv("FAISS_THRESHOLD_LOOKUP", 0.54))
FAISS_THRESHOLD_EXPLORATORY = float(os.getenv("FAISS_THRESHOLD_EXPLORATORY", 0.649))
MAX_FAISS_RESULTS = int(os.getenv("MAX_FAISS_RESULTS", 10))
LOG_DROPPED_NOTES = _bool_env("LOG_DROPPED_NOTES", False)

# intent cache
INTENT_CACHE_MAX_SIZE = int(os.getenv("INTENT_CACHE_MAX_SIZE", 1000))
INTENT_CACHE_TTL = int(os.getenv("INTENT_CACHE_TTL", 300))
INTENT_CACHE_LOG_HITS = _bool_env("INTENT_CACHE_LOG_HITS", False)

# memory analytics (per-query logging)
MEMORY_ANALYTICS_ENABLED = os.getenv("MEMORY_ANALYTICS_ENABLED", "false").lower() == "true"
MEMORY_ANALYTICS_FORMAT = os.getenv("MEMORY_ANALYTICS_FORMAT", "csv")
MEMORY_ANALYTICS_PATH = os.getenv("MEMORY_ANALYTICS_PATH", "data/memory_analytics.csv")

# Notes: body size cap (create + PDF extract) and PDF upload size
NOTES_MAX_CONTENT_CHARS = int(os.getenv("NOTES_MAX_CONTENT_CHARS", "512000"))
NOTES_PDF_MAX_BYTES = int(os.getenv("NOTES_PDF_MAX_BYTES", str(15 * 1024 * 1024)))
NOTES_PDF_MAX_EXTRACT_CHARS = int(os.getenv("NOTES_PDF_MAX_EXTRACT_CHARS", str(NOTES_MAX_CONTENT_CHARS)))
NOTES_PPTX_MAX_BYTES = int(os.getenv("NOTES_PPTX_MAX_BYTES", str(15 * 1024 * 1024)))
NOTES_IMAGE_MAX_BYTES = int(os.getenv("NOTES_IMAGE_MAX_BYTES", str(8 * 1024 * 1024)))
NOTES_IMAGE_MAX_TOTAL_BYTES = int(os.getenv("NOTES_IMAGE_MAX_TOTAL_BYTES", str(32 * 1024 * 1024)))
NOTES_IMAGE_MAX_COUNT = int(os.getenv("NOTES_IMAGE_MAX_COUNT", "20"))

# CORS: comma-separated origins (e.g. Vite dev). Empty = no CORS. Default allows localhost:5174.
CORS_ORIGINS = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5174,http://127.0.0.1:5174").split(",") if o.strip()]
