# IA/backend/app/__init__.py

import logging
from pathlib import Path
from flask import Flask, send_from_directory, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import CORS_ORIGINS, validate_jwt_secret

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://",
)

def create_app():
    """Flask application factory. Serves API + frontend (Phase 5). Prefers built React SPA (frontend/dist) when present."""
    validate_jwt_secret()
    app = Flask(__name__)
    limiter.init_app(app)
    if CORS_ORIGINS:
        CORS(app, origins=CORS_ORIGINS, supports_credentials=True)

    frontend_root = Path(__file__).resolve().parent.parent.parent / "frontend"
    dist = frontend_root / "dist"
    if (dist / "index.html").exists():
        app.static_folder = str(dist)
        app.static_url_path = ""

        @app.route("/assets/<path:filename>")
        def vite_assets(filename):
            return send_from_directory(dist / "assets", filename)
    else:
        app.static_folder = str(frontend_root)
        app.static_url_path = ""

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/privacy")
    @app.route("/terms")
    @app.route("/contact")
    @app.route("/login")
    @app.route("/register")
    @app.route("/ask")
    @app.route("/manage")
    @app.route("/debug")
    @app.route("/settings")
    @app.route("/app")
    def frontend_page():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/health", methods=["GET"])
    def health():
        """Phase 6: deploy probes; no auth."""
        return {"status": "ok"}, 200

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.after_request
    def request_log(response):
        """Phase 6: structured request log (method, path, status); no secrets."""
        logger.info("request method=%s path=%s status=%s", request.method, request.path, response.status_code)
        return response

    from app.notes.routes import bp as notes_bp
    from app.ai.routes import bp as ai_bp
    from app.files.routes import bp as files_bp
    from app.settings.routes import bp as settings_bp
    from app.auth.routes import bp as auth_bp
    from app.credits.routes import bp as credits_bp
    from app.memories.routes import bp as memories_bp
    from app.activity.routes import bp as activity_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(ai_bp, url_prefix="/ai")
    app.register_blueprint(files_bp, url_prefix="/files")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(credits_bp, url_prefix="/credits")
    app.register_blueprint(memories_bp, url_prefix="/memories")
    app.register_blueprint(activity_bp, url_prefix="/activity")
    return app

# single root logger for app (avoid duplicate basicConfig per import)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IA")
