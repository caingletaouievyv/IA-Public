# IA/backend/run.py

from pathlib import Path
from dotenv import load_dotenv

# Load .env from repo root (one place for backend + frontend)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

from app import create_app
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
