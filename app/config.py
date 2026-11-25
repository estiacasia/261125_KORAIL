import os
import secrets
import warnings


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///mailgen.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = None
    JSON_AS_ASCII = False
    SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed_catalog.json")

    @classmethod
    def ensure_secret(cls, app):
        if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "change-me-to-a-random-string":
            if not app.config.get("TESTING"):
                warnings.warn("SECRET_KEY가 .env에 설정되지 않아 임시 키를 사용합니다.")
            app.config["SECRET_KEY"] = secrets.token_hex(32)
