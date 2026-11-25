import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from ..catalog import build_admin_tree, build_catalog, catalog_rev
from ..extensions import db
from ..models import (
    BLOCKS,
    SIG_KEYS,
    Audience,
    Chip,
    Contact,
    History,
    NoticeRow,
    Preset,
    Project,
    Situation,
    TemplateVariant,
    VariantRevision,
    bump_catalog_rev,
    get_setting,
    KST,
    get_sig,
    now_str,
    set_setting,
)
from ..renderer import normalize, render, validate_state
from ..validation import ValidationError, text_warnings, validate_inputs, validate_sig

bp = Blueprint("api", __name__)

_cache = {"rev": None, "data": None}
PRESET_MAX = 20


# ---------------------------------------------------------------- helpers
def err(message, code="VALIDATION_ERROR", field=None, status=400):
    e = {"code": code, "message": message}
    if field:
        e["field"] = field
    return jsonify(error=e), status


@bp.errorhandler(ValidationError)
def _verr(e):
    return err(e.message, field=e.field)


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("JSON 본문이 필요합니다.")
    return data


def get_catalog():
    rev = catalog_rev()
    if _cache["rev"] != rev or _cache["data"] is None:
        _cache["data"] = build_catalog()
        _cache["rev"] = rev
    return _cache["data"]


def invalidate():
    _cache["rev"] = None


def _str(d, key, maxlen, required=False, label=None):
    v = d.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ValidationError(f"{label or key} 형식이 올바르지 않습니다.", key)
    v = v.strip()
    if required and not v:
        raise ValidationError(f"{label or key}을(를) 입력해 주세요.", key)
    if len(v) > maxlen:
        raise ValidationError(f"{label or key}은(는) {maxlen}자 이하로 입력해 주세요.", key)
    return v


def prepare_state(data):
    """state 검증 + 정규화. sig는 state.sig > 설정 순."""
    state = data.get("state")
    cat = get_catalog()
    bad = validate_state(cat, state)
    if bad:
        raise ValidationError(*bad)
    validate_inputs(cat, state.get("f") or {})
    sig = data.get("sig", state.get("sig"))
    validate_sig(sig)
    if sig is None:
        sig = get_sig()
    st = normalize(state)
    st.pop("sig", None)
    return cat, st, sig


def _month(data):
    m = data.get("month")
    return m if isinstance(m, int) and 1 <= m <= 12 else None


# ---------------------------------------------------------------- catalog / render
@bp.get("/catalog")
def catalog():
    return jsonify({**get_catalog(), "rev": catalog_rev()})


@bp.post("/render")
def render_api():
    data = body()
    cat, st, sig = prepare_state(data)
    r = render(cat, st, sig, month=_month(data))
    return jsonify(subject=r["subject"], body=r["body"], subjectHtml=r["subjectHtml"], bodyHtml=r["bodyHtml"], tag=r["tag"])


# ---------------------------------------------------------------- history
def history_dict(h, full=False):
    d = {
        "id": h.id, "mode": h.mode, "situation_code": h.situation_code, "audience": h.audience, "tone": h.tone,
        "channel": h.channel, "to_name": h.to_name, "project_name": h.project_name, "subject": h.subject,
        "is_edited": bool(h.is_edited), "action": h.action, "is_favorite": bool(h.is_favorite), "created_at": h.created_at,
        "label": history_label(h),
    }
    if full:
        d["body"] = h.body
        d["catalog_rev"] = h.catalog_rev
        d["snapshot"] = history_snapshot(h)
    return d


def history_label(h):
    cat = get_catalog()
    sits = cat[h.mode]["sits"] if h.mode in ("email", "notice") else {}
    name = sits.get(h.situation_code, {}).get("name", h.situation_code)
    tone = "격식" if h.tone == "formal" else "실무"
    if h.mode == "email":
        return f"{name} · {cat['aud'].get(h.audience or '', {}).get('name', '')} · {tone}"
    return f"공지 · {name} · {cat['notice']['fmtName'].get(h.channel or '', '')} · {tone}"


def history_snapshot(h):
    return {
        "mode": h.mode, "sit": {h.mode: h.situation_code}, "aud": h.audience or "ext", "tone": h.tone,
        "fmt": h.channel or "board", "f": json.loads(h.inputs_json), "chips": json.loads(h.chips_json),
        "tg": json.loads(h.toggles_json), "v": json.loads(h.variant_seed_json),
    }


def _touch_usage(to_name, project_name):
    ts = now_str()
    if to_name:
        for c in Contact.query.filter_by(display_name=to_name).all():
            c.use_count += 1
            c.last_used_at = ts
    if project_name:
        p = Project.query.filter_by(name=project_name).first()
        if p:
            p.use_count += 1
            p.last_used_at = ts


@bp.post("/history")
def history_create():
    data = body()
    action = data.get("action", "copy")
    if action not in ("copy", "mailto", "draft"):
        raise ValidationError("action 값이 올바르지 않습니다.", "action")
    cat, st, sig = prepare_state(data)
    r = render(cat, st, sig, month=_month(data))
    subject, text, edited = r["subject"], r["body"], 0
    ed = data.get("edited")
    if ed:
        if not isinstance(ed, dict):
            raise ValidationError("수정본 형식이 올바르지 않습니다.", "edited")
        subject = _str(ed, "subject", 500, label="제목")
        text = ed.get("body")
        if not isinstance(text, str) or len(text) > 20000:
            raise ValidationError("수정본 본문이 올바르지 않습니다.", "edited.body")
        edited = 1

    cutoff = (datetime.now(KST) - timedelta(seconds=3)).strftime("%Y-%m-%d %H:%M:%S")
    dup = (History.query.filter(History.subject == subject, History.body == text, History.created_at >= cutoff)
           .order_by(History.id.desc()).first())
    if dup:
        return jsonify(history_dict(dup) | {"duplicate": True}), 200

    to_name = (st["f"].get("to") or "").strip() if st["mode"] == "email" else ""
    proj = (st["f"].get("proj") or "").strip() if st["mode"] == "email" else ""
    h = History(
        mode=st["mode"], situation_code=st["sit"][st["mode"]], audience=st["aud"] if st["mode"] == "email" else None,
        tone=st["tone"], channel=st["fmt"] if st["mode"] == "notice" else None,
        inputs_json=json.dumps(st["f"], ensure_ascii=False), chips_json=json.dumps(st["chips"], ensure_ascii=False),
        toggles_json=json.dumps(st["tg"], ensure_ascii=False), variant_seed_json=json.dumps(st["v"]),
        catalog_rev=catalog_rev(), to_name=to_name or None, project_name=proj or None,
        subject=subject, body=text, is_edited=edited, action=action, created_at=now_str(),
    )
    db.session.add(h)
    _touch_usage(to_name, proj)
    db.session.commit()
    return jsonify(history_dict(h)), 201


def history_query(args):
    q = History.query
    kw = (args.get("q") or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(History.to_name.ilike(like), History.project_name.ilike(like), History.subject.ilike(like), History.body.ilike(like)))
    if args.get("mode") in ("email", "notice"):
        q = q.filter(History.mode == args["mode"])
    if args.get("sit"):
        q = q.filter(History.situation_code == args["sit"])
    if args.get("fav") in ("1", "true"):
        q = q.filter(History.is_favorite == 1)
    return q.order_by(History.created_at.desc(), History.id.desc())


@bp.get("/history")
def history_list():
    q = history_query(request.args)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)
    page = max(request.args.get("page", 1, type=int), 1)
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return jsonify(items=[history_dict(h) for h in items], total=total, page=page, limit=limit)


@bp.get("/history/<int:hid>")
def history_get(hid):
    h = db.session.get(History, hid)
    if not h:
        return err("기록을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    return jsonify(history_dict(h, full=True))


@bp.patch("/history/<int:hid>")
def history_patch(hid):
    h = db.session.get(History, hid)
    if not h:
        return err("기록을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    data = body()
    if "is_favorite" in data:
        h.is_favorite = 1 if data["is_favorite"] else 0
    db.session.commit()
    return jsonify(history_dict(h))


@bp.delete("/history/<int:hid>")
def history_delete(hid):
    h = db.session.get(History, hid)
    if not h:
        return err("기록을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(h)
    db.session.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- presets
def preset_dict(p):
    snap = json.loads(p.snapshot_json)
    return {"id": p.id, "name": p.name, "snapshot": snap, "created_at": p.created_at, "updated_at": p.updated_at}


def _preset_payload(data):
    name = _str(data, "name", 40, required=True, label="프리셋 이름")
    snap = data.get("snapshot")
    cat = get_catalog()
    bad = validate_state(cat, snap)
    if bad:
        raise ValidationError(*bad)
    validate_inputs(cat, snap.get("f") or {})
    snap = normalize(snap)
    snap.pop("sig", None)
    return name, snap


@bp.get("/presets")
def presets_list():
    return jsonify(items=[preset_dict(p) for p in Preset.query.order_by(Preset.updated_at.desc(), Preset.id.desc()).all()])


@bp.get("/presets/<int:pid>")
def presets_get(pid):
    p = db.session.get(Preset, pid)
    if not p:
        return err("프리셋을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    return jsonify(preset_dict(p))


@bp.post("/presets")
def presets_create():
    name, snap = _preset_payload(body())
    ts = now_str()
    p = Preset(name=name, snapshot_json=json.dumps(snap, ensure_ascii=False), created_at=ts, updated_at=ts)
    db.session.add(p)
    db.session.flush()
    extra = Preset.query.order_by(Preset.updated_at.desc(), Preset.id.desc()).offset(PRESET_MAX).all()
    for x in extra:
        db.session.delete(x)
    db.session.commit()
    return jsonify(preset_dict(p)), 201


@bp.put("/presets/<int:pid>")
def presets_update(pid):
    p = db.session.get(Preset, pid)
    if not p:
        return err("프리셋을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    name, snap = _preset_payload(body())
    p.name, p.snapshot_json, p.updated_at = name, json.dumps(snap, ensure_ascii=False), now_str()
    db.session.commit()
    return jsonify(preset_dict(p))


@bp.delete("/presets/<int:pid>")
def presets_delete(pid):
    p = db.session.get(Preset, pid)
    if not p:
        return err("프리셋을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- contacts / projects
def contact_dict(c):
    return {"id": c.id, "display_name": c.display_name, "company": c.company, "email": c.email,
            "default_audience": c.default_audience, "use_count": c.use_count, "last_used_at": c.last_used_at}


def project_dict(p):
    return {"id": p.id, "name": p.name, "is_archived": bool(p.is_archived), "use_count": p.use_count, "last_used_at": p.last_used_at}


def _contact_payload(data, c):
    c.display_name = _str(data, "display_name", 50, required=True, label="이름")
    c.company = _str(data, "company", 100, label="회사") or None
    c.email = _str(data, "email", 200, label="이메일") or None
    aud = data.get("default_audience") or None
    if aud is not None and db.session.get(Audience, aud) is None:
        raise ValidationError("기본 수신 대상이 올바르지 않습니다.", "default_audience")
    c.default_audience = aud


@bp.get("/contacts")
def contacts_list():
    q = Contact.query
    kw = (request.args.get("q") or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(Contact.display_name.ilike(like), Contact.company.ilike(like), Contact.email.ilike(like)))
        q = q.order_by(Contact.use_count.desc(), Contact.last_used_at.desc()).limit(8)
    elif request.args.get("all") != "1":
        q = q.order_by(Contact.use_count.desc(), Contact.last_used_at.desc()).limit(8)
    else:
        q = q.order_by(Contact.display_name)
    return jsonify(items=[contact_dict(c) for c in q.all()])


@bp.post("/contacts")
def contacts_create():
    c = Contact()
    _contact_payload(body(), c)
    db.session.add(c)
    db.session.commit()
    return jsonify(contact_dict(c)), 201


@bp.put("/contacts/<int:cid>")
def contacts_update(cid):
    c = db.session.get(Contact, cid)
    if not c:
        return err("주소록 항목을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    _contact_payload(body(), c)
    db.session.commit()
    return jsonify(contact_dict(c))


@bp.delete("/contacts/<int:cid>")
def contacts_delete(cid):
    c = db.session.get(Contact, cid)
    if not c:
        return err("주소록 항목을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/projects")
def projects_list():
    q = Project.query
    kw = (request.args.get("q") or "").strip()
    if kw:
        q = q.filter(Project.name.ilike(f"%{kw}%"), Project.is_archived == 0).order_by(Project.use_count.desc(), Project.last_used_at.desc()).limit(8)
    elif request.args.get("all") != "1":
        q = q.filter(Project.is_archived == 0).order_by(Project.use_count.desc(), Project.last_used_at.desc()).limit(8)
    else:
        q = q.order_by(Project.is_archived, Project.name)
    return jsonify(items=[project_dict(p) for p in q.all()])


def _project_payload(data, p):
    name = _str(data, "name", 100, required=True, label="프로젝트명")
    dup = Project.query.filter(Project.name == name, Project.id != (p.id or 0)).first()
    if dup:
        raise ValidationError("같은 이름의 프로젝트가 이미 있습니다.", "name")
    p.name = name
    if "is_archived" in data:
        p.is_archived = 1 if data["is_archived"] else 0


@bp.post("/projects")
def projects_create():
    p = Project()
    _project_payload(body(), p)
    db.session.add(p)
    db.session.commit()
    return jsonify(project_dict(p)), 201


@bp.put("/projects/<int:pid>")
def projects_update(pid):
    p = db.session.get(Project, pid)
    if not p:
        return err("프로젝트를 찾을 수 없습니다.", "NOT_FOUND", status=404)
    _project_payload(body(), p)
    db.session.commit()
    return jsonify(project_dict(p))


@bp.delete("/projects/<int:pid>")
def projects_delete(pid):
    p = db.session.get(Project, pid)
    if not p:
        return err("프로젝트를 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- settings
DEFAULT_CHOICES = {
    "default_mode": ("email", "notice"),
    "default_tone": ("formal", "brief"),
    "default_audience": ("ext", "dept", "team"),
    "default_channel": ("board", "slack", "kakao"),
}


def settings_dict():
    d = {"sig": get_sig()}
    for k, choices in DEFAULT_CHOICES.items():
        d[k] = get_setting(k, choices[0])
    return d


@bp.get("/settings")
def settings_get():
    return jsonify(settings_dict())


@bp.put("/settings")
def settings_put():
    data = body()
    if "sig" in data:
        sig = data["sig"]
        validate_sig(sig)
        for k in SIG_KEYS:
            if k in sig:
                set_setting("sig_" + k, (sig[k] or "").strip())
    for k, choices in DEFAULT_CHOICES.items():
        if k in data:
            if data[k] not in choices:
                raise ValidationError("기본값이 올바르지 않습니다.", k)
            set_setting(k, data[k])
    db.session.commit()
    return jsonify(settings_dict())


# ---------------------------------------------------------------- catalog admin
@bp.get("/catalog/admin")
def catalog_admin():
    return jsonify(tree=build_admin_tree(), rev=catalog_rev(), audiences=[{"code": a.code, "name": a.name} for a in Audience.query.order_by(Audience.sort_order)])


def _changed():
    rev = bump_catalog_rev()
    db.session.commit()
    invalidate()
    return rev


def _group_q(v):
    return TemplateVariant.query.filter_by(mode=v.mode, situation_id=v.situation_id, block=v.block, audience=v.audience, tone=v.tone)


def variant_dict(v):
    return {"id": v.id, "text": v.text, "is_active": bool(v.is_active), "sort_order": v.sort_order, "block": v.block,
            "situation_id": v.situation_id, "audience": v.audience, "tone": v.tone, "mode": v.mode}


@bp.post("/catalog/variants")
def variants_create():
    data = body()
    mode, block = data.get("mode"), data.get("block")
    if mode not in ("email", "notice") or block not in BLOCKS:
        raise ValidationError("모드 또는 블록이 올바르지 않습니다.", "block")
    sid = data.get("situation_id")
    if sid is not None and db.session.get(Situation, sid) is None:
        raise ValidationError("상황을 찾을 수 없습니다.", "situation_id")
    tone = data.get("tone")
    if tone not in ("formal", "brief", None):
        raise ValidationError("톤이 올바르지 않습니다.", "tone")
    aud = data.get("audience")
    if aud is not None and db.session.get(Audience, aud) is None:
        raise ValidationError("수신 대상이 올바르지 않습니다.", "audience")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValidationError("문구를 2,000자 이내로 입력해 주세요.", "text")
    mx = db.session.query(func.max(TemplateVariant.sort_order)).filter_by(
        mode=mode, situation_id=sid, block=block, audience=aud, tone=tone).scalar()
    v = TemplateVariant(mode=mode, situation_id=sid, block=block, audience=aud, tone=tone, text=text,
                        sort_order=(mx if mx is not None else -1) + 1, updated_at=now_str())
    db.session.add(v)
    rev = _changed()
    return jsonify(variant=variant_dict(v), warnings=text_warnings(text), rev=rev), 201


@bp.put("/catalog/variants/<int:vid>")
def variants_update(vid):
    v = db.session.get(TemplateVariant, vid)
    if not v:
        return err("문구를 찾을 수 없습니다.", "NOT_FOUND", status=404)
    text = body().get("text")
    if not isinstance(text, str) or len(text) > 2000:
        raise ValidationError("문구를 2,000자 이내로 입력해 주세요.", "text")
    if text != v.text:
        db.session.add(VariantRevision(variant_id=v.id, old_text=v.text, created_at=now_str()))
        v.text = text
        v.updated_at = now_str()
        rev = _changed()
    else:
        rev = catalog_rev()
    return jsonify(variant=variant_dict(v), warnings=text_warnings(text), rev=rev)


@bp.patch("/catalog/variants/<int:vid>")
def variants_patch(vid):
    v = db.session.get(TemplateVariant, vid)
    if not v:
        return err("문구를 찾을 수 없습니다.", "NOT_FOUND", status=404)
    data = body()
    if "is_active" in data:
        active = 1 if data["is_active"] else 0
        if not active and v.is_active:
            n = _group_q(v).filter_by(is_active=1).count()
            if n <= 1:
                return err("블록마다 최소 1개의 활성 문구가 필요합니다.", "LAST_ACTIVE_VARIANT", status=409)
        v.is_active = active
    if data.get("move") in ("up", "down"):
        items = _group_q(v).order_by(TemplateVariant.sort_order, TemplateVariant.id).all()
        for i, x in enumerate(items):
            x.sort_order = i
        i = items.index(v)
        j = i - 1 if data["move"] == "up" else i + 1
        if 0 <= j < len(items):
            items[i].sort_order, items[j].sort_order = items[j].sort_order, items[i].sort_order
    v.updated_at = now_str()
    rev = _changed()
    return jsonify(variant=variant_dict(v), rev=rev)


@bp.get("/catalog/variants/<int:vid>/revisions")
def variants_revisions(vid):
    revs = VariantRevision.query.filter_by(variant_id=vid).order_by(VariantRevision.id.desc()).all()
    return jsonify(items=[{"id": r.id, "old_text": r.old_text, "created_at": r.created_at} for r in revs])


def chip_dict(c):
    return {"id": c.id, "situation_id": c.situation_id, "code": c.code, "label": c.label, "text_formal": c.text_formal,
            "text_brief": c.text_brief, "text": c.text, "default_on": bool(c.default_on), "sort_order": c.sort_order}


def _chip_payload(data, c):
    c.label = _str(data, "label", 40, required=True, label="칩 이름")
    for k in ("text_formal", "text_brief", "text"):
        if k in data:
            v = data[k]
            if v is not None and (not isinstance(v, str) or len(v) > 2000):
                raise ValidationError("칩 문구는 2,000자 이하입니다.", k)
            setattr(c, k, v)
    if "default_on" in data:
        c.default_on = 1 if data["default_on"] else 0
    return text_warnings("\n".join(x or "" for x in (c.text_formal, c.text_brief, c.text)))


@bp.post("/catalog/chips")
def chips_create():
    data = body()
    sit = db.session.get(Situation, data.get("situation_id") or 0)
    if not sit:
        raise ValidationError("상황을 찾을 수 없습니다.", "situation_id")
    code = _str(data, "code", 30, required=True, label="칩 코드")
    if Chip.query.filter_by(situation_id=sit.id, code=code).first():
        raise ValidationError("같은 코드의 칩이 이미 있습니다.", "code")
    mx = db.session.query(func.max(Chip.sort_order)).filter_by(situation_id=sit.id).scalar()
    c = Chip(situation_id=sit.id, code=code, sort_order=(mx if mx is not None else -1) + 1)
    w = _chip_payload(data, c)
    db.session.add(c)
    rev = _changed()
    return jsonify(chip=chip_dict(c), warnings=w, rev=rev), 201


@bp.put("/catalog/chips/<int:cid>")
def chips_update(cid):
    c = db.session.get(Chip, cid)
    if not c:
        return err("칩을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    w = _chip_payload(body(), c)
    rev = _changed()
    return jsonify(chip=chip_dict(c), warnings=w, rev=rev)


@bp.delete("/catalog/chips/<int:cid>")
def chips_delete(cid):
    c = db.session.get(Chip, cid)
    if not c:
        return err("칩을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(c)
    rev = _changed()
    return jsonify(ok=True, rev=rev)


def row_dict(r):
    return {"id": r.id, "situation_id": r.situation_id, "label": r.label, "token": r.token, "is_list": bool(r.is_list),
            "is_optional": bool(r.is_optional), "sort_order": r.sort_order}


def _row_payload(data, r):
    r.label = _str(data, "label", 30, required=True, label="행 라벨")
    r.token = _str(data, "token", 30, required=True, label="토큰")
    if not r.token.isidentifier():
        raise ValidationError("토큰은 영문·숫자·밑줄만 사용할 수 있습니다.", "token")
    if "is_list" in data:
        r.is_list = 1 if data["is_list"] else 0
    if "is_optional" in data:
        r.is_optional = 1 if data["is_optional"] else 0


@bp.post("/catalog/rows")
def rows_create():
    data = body()
    sit = db.session.get(Situation, data.get("situation_id") or 0)
    if not sit or sit.mode != "notice":
        raise ValidationError("공지 상황을 찾을 수 없습니다.", "situation_id")
    mx = db.session.query(func.max(NoticeRow.sort_order)).filter_by(situation_id=sit.id).scalar()
    r = NoticeRow(situation_id=sit.id, sort_order=(mx if mx is not None else -1) + 1)
    _row_payload(data, r)
    db.session.add(r)
    rev = _changed()
    return jsonify(row=row_dict(r), rev=rev), 201


@bp.put("/catalog/rows/<int:rid>")
def rows_update(rid):
    r = db.session.get(NoticeRow, rid)
    if not r:
        return err("행을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    _row_payload(body(), r)
    rev = _changed()
    return jsonify(row=row_dict(r), rev=rev)


@bp.patch("/catalog/rows/<int:rid>")
def rows_patch(rid):
    r = db.session.get(NoticeRow, rid)
    if not r:
        return err("행을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    data = body()
    if data.get("move") in ("up", "down"):
        items = NoticeRow.query.filter_by(situation_id=r.situation_id).order_by(NoticeRow.sort_order, NoticeRow.id).all()
        for i, x in enumerate(items):
            x.sort_order = i
        i = items.index(r)
        j = i - 1 if data["move"] == "up" else i + 1
        if 0 <= j < len(items):
            items[i].sort_order, items[j].sort_order = items[j].sort_order, items[i].sort_order
    rev = _changed()
    return jsonify(row=row_dict(r), rev=rev)


@bp.delete("/catalog/rows/<int:rid>")
def rows_delete(rid):
    r = db.session.get(NoticeRow, rid)
    if not r:
        return err("행을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    db.session.delete(r)
    rev = _changed()
    return jsonify(ok=True, rev=rev)


FIELD_KEYS = {"k", "l", "sub", "type", "ph", "half", "tok"}
FIELD_TYPES = {"text", "date", "time", "textarea", "url", "email"}


@bp.put("/catalog/situations/<int:sid>/fields")
def situation_fields(sid):
    sit = db.session.get(Situation, sid)
    if not sit:
        return err("상황을 찾을 수 없습니다.", "NOT_FOUND", status=404)
    fields = body().get("fields")
    if not isinstance(fields, list):
        raise ValidationError("fields는 배열이어야 합니다.", "fields")
    if sit.mode == "email":
        known = set(json.loads(get_setting("catalog_email_fields", "{}"))) | {"cands"}
        for k in fields:
            if k not in known:
                raise ValidationError(f"알 수 없는 이메일 필드: {k}", "fields")
    else:
        seen = set()
        for d in fields:
            if not isinstance(d, dict) or not isinstance(d.get("k"), str) or not d["k"].isidentifier() or not isinstance(d.get("l"), str):
                raise ValidationError("필드마다 k(영문 키)와 l(라벨)이 필요합니다.", "fields")
            if set(d) - FIELD_KEYS:
                raise ValidationError(f"허용되지 않은 속성: {', '.join(sorted(set(d) - FIELD_KEYS))}", "fields")
            if d.get("type", "text") not in FIELD_TYPES:
                raise ValidationError(f"알 수 없는 필드 타입: {d.get('type')}", "fields")
            if d["k"] in seen:
                raise ValidationError(f"중복된 필드 키: {d['k']}", "fields")
            seen.add(d["k"])
    sit.fields_json = json.dumps(fields, ensure_ascii=False)
    sit.updated_at = now_str()
    rev = _changed()
    return jsonify(fields=fields, rev=rev)
