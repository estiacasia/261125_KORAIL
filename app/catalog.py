"""seed_catalog.json ↔ DB 변환.

- seed_catalog(data): JSON → DB (이미 있는 code는 건너뜀, 재실행 안전)
- build_catalog(): DB → seed_catalog.json과 동일한 구조
"""
import json

from .extensions import db
from .models import (
    Audience,
    Chip,
    NoticeRow,
    OptionText,
    SeasonalGreeting,
    Setting,
    Situation,
    TemplateVariant,
    get_setting,
)

TONES = ("formal", "brief")
CHANNELS = ("board", "slack", "kakao")

# seed JSON 키 ↔ DB block
SIT_BLOCKS = {"subj": "subj", "intro": "intro", "core": "core", "coreMulti": "core_multi", "closeLead": "close_lead"}

DEFAULT_SETTINGS = {
    "sig_name": "이지은",
    "sig_title": "매니저",
    "sig_dept": "마케팅팀",
    "sig_company": "",
    "sig_phone": "010-1234-5678",
    "sig_email": "jieun@example.com",
    "default_mode": "email",
    "default_tone": "formal",
    "default_audience": "ext",
    "default_channel": "board",
    "catalog_rev": "1",
}


# ---------------------------------------------------------------- seed
def _add_variants(texts, **kw):
    for i, t in enumerate(texts):
        db.session.add(TemplateVariant(text=t, sort_order=i, **kw))


def _common_exists(mode, block, audience, tone):
    return (
        db.session.query(TemplateVariant.id)
        .filter_by(mode=mode, situation_id=None, block=block, audience=audience, tone=tone)
        .first()
        is not None
    )


def seed_catalog(data):
    """Return dict of counts that were inserted."""
    added = {"situations": 0, "variants_groups": 0, "settings": 0}

    for m, text in data["season"].items():
        if db.session.get(SeasonalGreeting, int(m)) is None:
            db.session.add(SeasonalGreeting(month=int(m), text=text))

    for i, (code, a) in enumerate(data["aud"].items()):
        if db.session.get(Audience, code) is None:
            db.session.add(Audience(code=code, name=a["name"], default_to=a["defTo"], sort_order=i))
    db.session.flush()

    # 이메일 공통 인사말·맺음말 (대상 × 톤)
    for block in ("greet", "close"):
        for aud, by_tone in data[block].items():
            for tone in TONES:
                if not _common_exists("email", block, aud, tone):
                    _add_variants(by_tone[tone], mode="email", situation_id=None, block=block, audience=aud, tone=tone)
                    added["variants_groups"] += 1

    for key, val in data["opt"].items():
        if db.session.get(OptionText, key) is None:
            if isinstance(val, str):
                db.session.add(OptionText(key=key, text=val))
            else:
                db.session.add(OptionText(key=key, text_formal=val.get("formal"), text_brief=val.get("brief")))

    # 이메일 상황
    email = data["email"]
    for order, code in enumerate(email["order"]):
        s = email["sits"][code]
        if Situation.query.filter_by(mode="email", code=code).first():
            continue
        sit = Situation(
            mode="email", code=code, name=s["name"], sort_order=order,
            memo_mode=s.get("memoMode"), memo_name=s.get("memoName"), memo_label=s.get("memoLabel"),
            memo_sub=s.get("memoSub"), memo_placeholder=s.get("memoPh"),
            fields_json=json.dumps(s.get("fields", []), ensure_ascii=False),
        )
        db.session.add(sit)
        db.session.flush()
        for jkey, block in SIT_BLOCKS.items():
            if jkey in s:
                for tone in TONES:
                    _add_variants(s[jkey][tone], mode="email", situation_id=sit.id, block=block, tone=tone)
        for i, c in enumerate(s.get("chips", [])):
            db.session.add(Chip(situation_id=sit.id, code=c["id"], label=c["label"], text_formal=c.get("formal"),
                                text_brief=c.get("brief"), default_on=1 if c.get("on") else 0, sort_order=i))
        added["situations"] += 1

    # 공지 공통 블록
    notice = data["notice"]
    for block in ("greet", "lead", "close"):
        for tone in TONES:
            if not _common_exists("notice", block, None, tone):
                _add_variants(notice[block][tone], mode="notice", situation_id=None, block=block, audience=None, tone=tone)
                added["variants_groups"] += 1

    for order, code in enumerate(notice["order"]):
        s = notice["sits"][code]
        if Situation.query.filter_by(mode="notice", code=code).first():
            continue
        sit = Situation(
            mode="notice", code=code, name=s["name"], sort_order=order,
            when_type=s.get("when"), when_label=s.get("whenLabel"),
            fields_json=json.dumps(s.get("fields", []), ensure_ascii=False),
        )
        db.session.add(sit)
        db.session.flush()
        _add_variants(s["subj"], mode="notice", situation_id=sit.id, block="subj", tone=None)
        for jkey, block in (("intro", "intro"), ("closeLead", "close_lead")):
            for tone in TONES:
                _add_variants(s[jkey][tone], mode="notice", situation_id=sit.id, block=block, tone=tone)
        for i, c in enumerate(s.get("chips", [])):
            db.session.add(Chip(situation_id=sit.id, code=c["id"], label=c["label"], text=c.get("text"),
                                default_on=1 if c.get("on") else 0, sort_order=i))
        for i, r in enumerate(s.get("rows", [])):
            db.session.add(NoticeRow(situation_id=sit.id, label=r["l"], token=r["tok"], is_list=1 if r.get("list") else 0,
                                     is_optional=1 if r.get("opt") else 0, sort_order=i))
        added["situations"] += 1

    defaults = dict(DEFAULT_SETTINGS)
    defaults["catalog_email_fields"] = json.dumps(data["emailFields"], ensure_ascii=False)
    defaults["catalog_fmt_name"] = json.dumps(notice["fmtName"], ensure_ascii=False)
    for k, v in defaults.items():
        if db.session.get(Setting, k) is None:
            db.session.add(Setting(key=k, value=v))
            added["settings"] += 1

    db.session.commit()
    return added


# ---------------------------------------------------------------- build
def _variants(mode, situation_id, block, audience=None, tone=None, active_only=True):
    q = TemplateVariant.query.filter_by(mode=mode, situation_id=situation_id, block=block, audience=audience, tone=tone)
    if active_only:
        q = q.filter_by(is_active=1)
    return [v.text for v in q.order_by(TemplateVariant.sort_order, TemplateVariant.id).all()]


def _by_tone(mode, situation_id, block, audience=None):
    return {t: _variants(mode, situation_id, block, audience, t) for t in TONES}


def build_catalog():
    out = {}
    out["season"] = {str(g.month): g.text for g in SeasonalGreeting.query.order_by(SeasonalGreeting.month).all()}
    auds = Audience.query.order_by(Audience.sort_order).all()
    out["aud"] = {a.code: {"name": a.name, "defTo": a.default_to} for a in auds}
    out["greet"] = {a.code: _by_tone("email", None, "greet", a.code) for a in auds}
    out["close"] = {a.code: _by_tone("email", None, "close", a.code) for a in auds}

    opt = {}
    for o in OptionText.query.all():
        opt[o.key] = o.text if o.text is not None else {"formal": o.text_formal, "brief": o.text_brief}
    out["opt"] = opt
    out["emailFields"] = json.loads(get_setting("catalog_email_fields", "{}"))

    sits = Situation.query.filter_by(mode="email", is_active=1).order_by(Situation.sort_order, Situation.id).all()
    email = {"order": [s.code for s in sits], "sits": {}}
    for s in sits:
        d = {"name": s.name, "fields": json.loads(s.fields_json or "[]"), "memoMode": s.memo_mode,
             "memoName": s.memo_name, "memoLabel": s.memo_label}
        if s.memo_sub:
            d["memoSub"] = s.memo_sub
        d["memoPh"] = s.memo_placeholder
        for jkey, block in SIT_BLOCKS.items():
            bt = _by_tone("email", s.id, block)
            if jkey == "coreMulti" and not any(bt.values()):
                continue
            d[jkey] = bt
        chips = []
        for c in s.chips:
            cd = {"id": c.code, "label": c.label}
            if c.default_on:
                cd["on"] = 1
            cd["formal"] = c.text_formal or ""
            cd["brief"] = c.text_brief or ""
            chips.append(cd)
        d["chips"] = chips
        email["sits"][s.code] = d
    out["email"] = email

    nsits = Situation.query.filter_by(mode="notice", is_active=1).order_by(Situation.sort_order, Situation.id).all()
    notice = {"order": [s.code for s in nsits], "fmtName": json.loads(get_setting("catalog_fmt_name", "{}"))}
    for block in ("greet", "lead", "close"):
        notice[block] = _by_tone("notice", None, block)
    notice["sits"] = {}
    for s in nsits:
        rows = []
        for r in s.rows:
            rd = {"l": r.label, "tok": r.token}
            if r.is_list:
                rd["list"] = 1
            if r.is_optional:
                rd["opt"] = 1
            rows.append(rd)
        chips = []
        for c in s.chips:
            cd = {"id": c.code, "label": c.label}
            if c.default_on:
                cd["on"] = 1
            cd["text"] = c.text or ""
            chips.append(cd)
        notice["sits"][s.code] = {
            "name": s.name, "when": s.when_type, "whenLabel": s.when_label,
            "fields": json.loads(s.fields_json or "[]"), "rows": rows,
            "subj": _variants("notice", s.id, "subj"),
            "intro": _by_tone("notice", s.id, "intro"),
            "chips": chips,
            "closeLead": _by_tone("notice", s.id, "close_lead"),
        }
    out["notice"] = notice
    return out


def catalog_rev():
    return int(get_setting("catalog_rev", "1") or 1)


# ---------------------------------------------------------------- admin tree
def _vdict(v):
    return {"id": v.id, "text": v.text, "is_active": bool(v.is_active), "sort_order": v.sort_order}


def _group(mode, situation_id, block, audience=None, tone=None, label=""):
    q = TemplateVariant.query.filter_by(mode=mode, situation_id=situation_id, block=block, audience=audience, tone=tone)
    items = [_vdict(v) for v in q.order_by(TemplateVariant.sort_order, TemplateVariant.id).all()]
    return {"mode": mode, "situation_id": situation_id, "block": block, "audience": audience, "tone": tone,
            "label": label, "variants": items}


BLOCK_LABEL = {"subj": "제목", "greet": "인사말", "intro": "본론 도입", "core": "핵심 내용", "core_multi": "핵심 내용(후보 복수)",
               "close_lead": "상황별 마무리", "close": "맺음말", "lead": "리드 문구"}
TONE_LABEL = {"formal": "격식", "brief": "실무", None: "톤 공통"}


def build_admin_tree():
    auds = Audience.query.order_by(Audience.sort_order).all()
    tree = {"email": {"common": [], "situations": []}, "notice": {"common": [], "situations": []}}
    for block in ("greet", "close"):
        for a in auds:
            for t in TONES:
                tree["email"]["common"].append(_group("email", None, block, a.code, t, f"{BLOCK_LABEL[block]} · {a.name} · {TONE_LABEL[t]}"))
    for block in ("greet", "lead", "close"):
        for t in TONES:
            tree["notice"]["common"].append(_group("notice", None, block, None, t, f"{BLOCK_LABEL[block]} · {TONE_LABEL[t]}"))

    for s in Situation.query.order_by(Situation.mode, Situation.sort_order, Situation.id).all():
        groups = []
        if s.mode == "email":
            for block in ("subj", "intro", "core", "core_multi", "close_lead"):
                for t in TONES:
                    g = _group("email", s.id, block, None, t, f"{BLOCK_LABEL[block]} · {TONE_LABEL[t]}")
                    if block == "core_multi" and not g["variants"] and s.code != "schedule":
                        continue
                    groups.append(g)
        else:
            groups.append(_group("notice", s.id, "subj", None, None, "제목 · 톤 공통"))
            for block in ("intro", "close_lead"):
                for t in TONES:
                    groups.append(_group("notice", s.id, block, None, t, f"{BLOCK_LABEL[block]} · {TONE_LABEL[t]}"))
        tree[s.mode]["situations"].append({
            "id": s.id, "code": s.code, "name": s.name, "mode": s.mode,
            "fields": json.loads(s.fields_json or "[]"),
            "groups": groups,
            "chips": [{"id": c.id, "code": c.code, "label": c.label, "text_formal": c.text_formal, "text_brief": c.text_brief,
                       "text": c.text, "default_on": bool(c.default_on), "sort_order": c.sort_order} for c in s.chips],
            "rows": [{"id": r.id, "label": r.label, "token": r.token, "is_list": bool(r.is_list), "is_optional": bool(r.is_optional),
                      "sort_order": r.sort_order} for r in s.rows],
        })
    return tree
