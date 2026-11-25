import os
import sqlite3

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import Config
from .extensions import csrf, db


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


def _configure_database(app):
    """Postgres(Supabase) URL을 순수 Python 드라이버 pg8000용으로 맞추고, 서버리스용 풀 설정."""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if uri.startswith(prefix):
            uri = "postgresql+pg8000://" + uri[len(prefix):]
            break
    if uri.startswith("postgresql+pg8000://"):
        # pg8000은 sslmode 쿼리 인자를 모르므로 제거하고 ssl_context로 전달
        base, _, query = uri.partition("?")
        params = [p for p in query.split("&") if p and not p.startswith("sslmode=")]
        uri = base + ("?" + "&".join(params) if params else "")
        opts = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
        opts.setdefault("connect_args", {"ssl_context": True})
        opts.setdefault("pool_pre_ping", True)
        if os.environ.get("VERCEL"):
            from sqlalchemy.pool import NullPool

            opts["poolclass"] = NullPool
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = opts
    app.config["SQLALCHEMY_DATABASE_URI"] = uri


def create_app(test_config=None):
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    # .env는 Config 클래스가 import된 뒤에 읽히므로 여기서 다시 반영
    if os.environ.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    if os.environ.get("DATABASE_URL"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    if test_config:
        app.config.update(test_config)
    _configure_database(app)
    Config.ensure_secret(app)
    app.json.ensure_ascii = False
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass  # Vercel 등 읽기 전용 파일 시스템

    db.init_app(app)
    csrf.init_app(app)

    from .views.api import bp as api_bp
    from .views.pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    from .cli import register_cli

    register_cli(app)

    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        if request.path.startswith("/api"):
            return jsonify(error={"code": "CSRF_ERROR", "message": "보안 토큰이 만료되었습니다. 새로고침 후 다시 시도해 주세요."}), 400
        return e.description, 400

    return app
