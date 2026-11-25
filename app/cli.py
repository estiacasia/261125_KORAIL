import json

import click
from flask import current_app

from .catalog import build_catalog, seed_catalog
from .extensions import db


def load_seed(path=None):
    with open(path or current_app.config["SEED_PATH"], encoding="utf-8") as f:
        return json.load(f)


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """테이블 생성 (있으면 유지)."""
        from . import models  # noqa: F401

        db.create_all()
        click.echo("데이터베이스 테이블을 준비했습니다.")

    @app.cli.command("seed")
    @click.option("--file", "path", default=None, help="seed JSON 경로 (기본: data/seed_catalog.json)")
    def seed(path):
        """seed_catalog.json → DB. 이미 있는 code는 건너뜁니다."""
        db.create_all()
        added = seed_catalog(load_seed(path))
        click.echo(f"seed 완료: 상황 {added['situations']}개, 공통 블록 {added['variants_groups']}개, 설정 {added['settings']}개 추가")

    @app.cli.command("reset-db")
    @click.option("--yes", is_flag=True, help="확인 없이 실행")
    def reset_db(yes):
        """전체 삭제 → 생성 → seed."""
        if not yes and not click.confirm("모든 데이터(이력·프리셋·주소록 포함)를 삭제하고 초기화할까요?"):
            click.echo("취소했습니다.")
            return
        db.drop_all()
        db.create_all()
        seed_catalog(load_seed())
        click.echo("데이터베이스를 초기화했습니다.")

    @app.cli.command("export-catalog")
    @click.argument("path", required=False)
    def export_catalog(path):
        """현재 DB 문구를 seed와 같은 JSON 구조로 내보냅니다."""
        text = json.dumps(build_catalog(), ensure_ascii=False, indent=1)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            click.echo(f"{path}에 내보냈습니다.")
        else:
            click.echo(text)
