"""SQLAlchemy 모델 + seed_catalog.json → Supabase 마이그레이션 SQL 생성.

    python scripts/export_supabase_sql.py

supabase/migrations/ 에 스키마(RLS 포함)와 seed 데이터 SQL을 만든다.
적용: supabase db push
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import insert, select  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app import create_app  # noqa: E402
from app.catalog import seed_catalog  # noqa: E402
from app.cli import load_seed  # noqa: E402
from app.extensions import db  # noqa: E402

PG = postgresql.dialect(paramstyle="named")  # format 계열은 % 를 %% 로 이스케이프함
OUT = os.path.join(ROOT, "supabase", "migrations")
SEED_TABLES = ["audiences", "situations", "template_variants", "chips", "notice_rows", "seasonal_greetings", "option_texts", "settings"]


def main():
    tmp = os.path.join(tempfile.mkdtemp(), "export.sqlite3").replace("\\", "/")
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp})
    with app.app_context():
        db.create_all()
        seed_catalog(load_seed())
        md = db.metadata

        schema = ["-- 테이블·인덱스 (app/models.py 에서 생성)"]
        for t in md.sorted_tables:
            schema.append(str(CreateTable(t).compile(dialect=PG)).strip() + ";")
            for ix in sorted(t.indexes, key=lambda i: i.name):
                schema.append(str(CreateIndex(ix).compile(dialect=PG)).strip() + ";")
        schema.append("\n-- 앱은 postgres 역할로 직접 접속하므로 RLS를 켜서 공개 API(anon 키) 접근을 막는다")
        for t in md.sorted_tables:
            schema.append(f"ALTER TABLE public.{t.name} ENABLE ROW LEVEL SECURITY;")

        seed = ["-- 문구 카탈로그 seed (data/seed_catalog.json)"]
        for name in SEED_TABLES:
            t = md.tables[name]
            rows = [dict(r._mapping) for r in db.session.execute(select(t)).all()]
            if rows:
                seed.append(str(insert(t).values(rows).compile(dialect=PG, compile_kwargs={"literal_binds": True})).strip() + ";")
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].name == "id":
                seed.append(f"SELECT setval(pg_get_serial_sequence('public.{name}', 'id'), COALESCE((SELECT MAX(id) FROM public.{name}), 1));")
        db.session.remove()
        db.engine.dispose()

    os.makedirs(OUT, exist_ok=True)
    for fname, lines in (("20261125000000_init_schema.sql", schema), ("20261125000100_seed_catalog.sql", seed)):
        with open(os.path.join(OUT, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n\n".join(lines) + "\n")
        print("wrote", fname)


if __name__ == "__main__":
    main()
