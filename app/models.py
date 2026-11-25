"""SQLite 스키마 (작업 지시서 3장)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from .extensions import db


KST = ZoneInfo("Asia/Seoul")


def now_str():
    """한국 시간 문자열 (서버가 UTC인 Vercel에서도 동일)."""
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


class Situation(db.Model):
    __tablename__ = "situations"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mode = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Integer, nullable=False, default=1)
    memo_mode = db.Column(db.Text)
    memo_name = db.Column(db.Text)
    memo_label = db.Column(db.Text)
    memo_sub = db.Column(db.Text)
    memo_placeholder = db.Column(db.Text)
    when_type = db.Column(db.Text)
    when_label = db.Column(db.Text)
    fields_json = db.Column(db.Text, nullable=False, default="[]")
    updated_at = db.Column(db.Text, nullable=False, default=now_str)

    chips = db.relationship("Chip", backref="situation", cascade="all, delete-orphan", order_by="Chip.sort_order")
    rows = db.relationship("NoticeRow", backref="situation", cascade="all, delete-orphan", order_by="NoticeRow.sort_order")
    variants = db.relationship("TemplateVariant", backref="situation", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("mode", "code"),
        CheckConstraint("mode IN ('email','notice')"),
        CheckConstraint("memo_mode IN ('opt','core','chip')"),
        CheckConstraint("when_type IN ('dt','range','days')"),
    )


class Audience(db.Model):
    __tablename__ = "audiences"
    code = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    default_to = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (CheckConstraint("code IN ('ext','dept','team')"),)


BLOCKS = ("subj", "greet", "intro", "core", "core_multi", "close_lead", "close", "lead")


class TemplateVariant(db.Model):
    __tablename__ = "template_variants"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    situation_id = db.Column(db.Integer, db.ForeignKey("situations.id", ondelete="CASCADE"))
    mode = db.Column(db.Text, nullable=False)
    block = db.Column(db.Text, nullable=False)
    audience = db.Column(db.Text, db.ForeignKey("audiences.code"))
    tone = db.Column(db.Text)
    text = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.Text, nullable=False, default=now_str)

    revisions = db.relationship("VariantRevision", backref="variant", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("mode IN ('email','notice')"),
        CheckConstraint("block IN ('subj','greet','intro','core','core_multi','close_lead','close','lead')"),
        CheckConstraint("tone IN ('formal','brief')"),
        Index("idx_variant_lookup", "mode", "situation_id", "block", "audience", "tone", "is_active", "sort_order"),
    )


class VariantRevision(db.Model):
    __tablename__ = "variant_revisions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("template_variants.id", ondelete="CASCADE"), nullable=False)
    old_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, nullable=False, default=now_str)


class Chip(db.Model):
    __tablename__ = "chips"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    situation_id = db.Column(db.Integer, db.ForeignKey("situations.id", ondelete="CASCADE"), nullable=False)
    code = db.Column(db.Text, nullable=False)
    label = db.Column(db.Text, nullable=False)
    text_formal = db.Column(db.Text)
    text_brief = db.Column(db.Text)
    text = db.Column(db.Text)
    default_on = db.Column(db.Integer, nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("situation_id", "code"),)


class NoticeRow(db.Model):
    __tablename__ = "notice_rows"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    situation_id = db.Column(db.Integer, db.ForeignKey("situations.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.Text, nullable=False)
    token = db.Column(db.Text, nullable=False)
    is_list = db.Column(db.Integer, nullable=False, default=0)
    is_optional = db.Column(db.Integer, nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class SeasonalGreeting(db.Model):
    __tablename__ = "seasonal_greetings"
    month = db.Column(db.Integer, primary_key=True, autoincrement=False)
    text = db.Column(db.Text, nullable=False)
    __table_args__ = (CheckConstraint("month BETWEEN 1 AND 12"),)


class OptionText(db.Model):
    __tablename__ = "option_texts"
    key = db.Column(db.Text, primary_key=True)
    text_formal = db.Column(db.Text)
    text_brief = db.Column(db.Text)
    text = db.Column(db.Text)


class History(db.Model):
    __tablename__ = "history"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mode = db.Column(db.Text, nullable=False)
    situation_code = db.Column(db.Text, nullable=False)
    audience = db.Column(db.Text)
    tone = db.Column(db.Text, nullable=False)
    channel = db.Column(db.Text)
    inputs_json = db.Column(db.Text, nullable=False)
    chips_json = db.Column(db.Text, nullable=False)
    toggles_json = db.Column(db.Text, nullable=False)
    variant_seed_json = db.Column(db.Text, nullable=False)
    catalog_rev = db.Column(db.Integer)
    to_name = db.Column(db.Text)
    project_name = db.Column(db.Text)
    subject = db.Column(db.Text, nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_edited = db.Column(db.Integer, nullable=False, default=0)
    action = db.Column(db.Text, nullable=False)
    is_favorite = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.Text, nullable=False, default=now_str)
    __table_args__ = (
        CheckConstraint("action IN ('copy','mailto','draft')"),
        Index("idx_history_created", created_at.desc()),
        Index("idx_history_search", "to_name", "project_name"),
    )


class Preset(db.Model):
    __tablename__ = "presets"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    snapshot_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, nullable=False, default=now_str)
    updated_at = db.Column(db.Text, nullable=False, default=now_str)


class Contact(db.Model):
    __tablename__ = "contacts"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    display_name = db.Column(db.Text, nullable=False)
    company = db.Column(db.Text)
    email = db.Column(db.Text)
    default_audience = db.Column(db.Text, db.ForeignKey("audiences.code"))
    use_count = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.Text)
    created_at = db.Column(db.Text, nullable=False, default=now_str)


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    is_archived = db.Column(db.Integer, nullable=False, default=0)
    use_count = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.Text)
    created_at = db.Column(db.Text, nullable=False, default=now_str)


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.Text, primary_key=True)
    value = db.Column(db.Text)


SIG_KEYS = ("name", "title", "dept", "company", "phone", "email")


def get_setting(key, default=None):
    s = db.session.get(Setting, key)
    return s.value if s is not None and s.value is not None else default


def set_setting(key, value):
    s = db.session.get(Setting, key)
    if s is None:
        db.session.add(Setting(key=key, value=value))
    else:
        s.value = value


def get_sig():
    return {k: get_setting("sig_" + k, "") or "" for k in SIG_KEYS}


def bump_catalog_rev():
    rev = int(get_setting("catalog_rev", "1") or 1) + 1
    set_setting("catalog_rev", str(rev))
    return rev
