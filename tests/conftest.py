import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from app.catalog import seed_catalog  # noqa: E402
from app.extensions import db  # noqa: E402

SEED_PATH = os.path.join(ROOT, "data", "seed_catalog.json")


@pytest.fixture(scope="session")
def seed():
    with open(SEED_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def app(tmp_path, seed):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite3").replace("\\", "/"),
    })
    with app.app_context():
        db.create_all()
        seed_catalog(seed)
        from app.views import api

        api.invalidate()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def base_state(**kw):
    s = {
        "mode": "email", "sit": {"email": "delay", "notice": "internal"}, "aud": "ext", "tone": "formal", "fmt": "board",
        "f": {"to": "김민수 팀장님", "proj": "2027 브랜드 리뉴얼", "oldDate": "2026-12-04", "newDate": "2026-12-11",
              "memo.delay": "원자재 수급 지연", "files.email": "1차_시안.pdf"},
        "chips": {"email.delay": ["cause", "emph"]},
        "tg": {"attach.email": True, "attach.notice": False, "due": False, "sig": True},
        "v": {"subj": 0, "greet": 0, "intro": 0, "core": 0, "close": 0},
    }
    s.update(kw)
    return s
