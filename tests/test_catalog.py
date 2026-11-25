from app.catalog import build_catalog, seed_catalog
from app.models import Situation, TemplateVariant, VariantRevision, get_setting


def test_api_catalog_equals_seed(client, seed):
    data = client.get("/api/catalog").get_json()
    rev = data.pop("rev")
    assert rev == 1
    assert data == seed


def test_seed_is_idempotent(app, seed):
    n_var, n_sit = TemplateVariant.query.count(), Situation.query.count()
    added = seed_catalog(seed)
    assert added == {"situations": 0, "variants_groups": 0, "settings": 0}
    assert TemplateVariant.query.count() == n_var and Situation.query.count() == n_sit
    assert build_catalog() == seed


def _group_ids(app, mode, block, sit_code=None, tone="formal", audience=None):
    sid = Situation.query.filter_by(mode=mode, code=sit_code).first().id if sit_code else None
    return [v.id for v in TemplateVariant.query.filter_by(mode=mode, situation_id=sid, block=block, tone=tone, audience=audience)
            .order_by(TemplateVariant.sort_order).all()]


def test_last_active_variant_409(client, app):
    ids = _group_ids(app, "email", "subj", "delay")
    assert len(ids) == 3
    for vid in ids[:2]:
        assert client.patch(f"/api/catalog/variants/{vid}", json={"is_active": False}).status_code == 200
    r = client.patch(f"/api/catalog/variants/{ids[2]}", json={"is_active": False})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "LAST_ACTIVE_VARIANT"
    subj = client.get("/api/catalog").get_json()["email"]["sits"]["delay"]["subj"]["formal"]
    assert len(subj) == 1


def test_update_bumps_rev_and_records_revision(client, app):
    vid = _group_ids(app, "email", "intro", "coop")[0]
    from app.extensions import db

    old = db.session.get(TemplateVariant, vid).text
    r = client.put(f"/api/catalog/variants/{vid}", json={"text": "{proj} 관련 새 도입 문구입니다."})
    assert r.status_code == 200 and r.get_json()["rev"] == 2
    assert get_setting("catalog_rev") == "2"
    revs = VariantRevision.query.filter_by(variant_id=vid).all()
    assert [x.old_text for x in revs] == [old]
    cat = client.get("/api/catalog").get_json()
    assert cat["rev"] == 2
    assert cat["email"]["sits"]["coop"]["intro"]["formal"][0] == "{proj} 관련 새 도입 문구입니다."


def test_new_variant_joins_shuffle(client, app):
    r = client.post("/api/catalog/variants", json={"mode": "email", "situation_id": Situation.query.filter_by(code="remind").first().id,
                                                   "block": "subj", "tone": "brief", "text": "[{proj}] 새 제목"})
    assert r.status_code == 201
    assert client.get("/api/catalog").get_json()["email"]["sits"]["remind"]["subj"]["brief"][-1] == "[{proj}] 새 제목"


def test_josa_warning(client, app):
    vid = _group_ids(app, "email", "intro", "coop")[0]
    w = client.put(f"/api/catalog/variants/{vid}", json={"text": "{proj}를 진행합니다."}).get_json()["warnings"]
    assert any("조사 규칙" in x for x in w)
    w = client.put(f"/api/catalog/variants/{vid}", json={"text": "{proj} 관련 진행합니다. {proj}이번"}).get_json()["warnings"]
    assert w == []
    w = client.put(f"/api/catalog/variants/{vid}", json={"text": "{proj}와 {zzz}"}).get_json()["warnings"]
    assert len(w) == 2


def test_move_variant(client, app):
    ids = _group_ids(app, "notice", "greet", tone="brief")
    client.patch(f"/api/catalog/variants/{ids[1]}", json={"move": "up"})
    assert _group_ids(app, "notice", "greet", tone="brief")[:2] == [ids[1], ids[0]]


def test_chips_rows_fields(client, app):
    sid = Situation.query.filter_by(code="maint").first().id
    r = client.post("/api/catalog/chips", json={"situation_id": sid, "code": "vpn", "label": "VPN 안내", "text": "※ VPN도 중단됩니다."})
    assert r.status_code == 201
    assert client.get("/api/catalog").get_json()["notice"]["sits"]["maint"]["chips"][-1] == {"id": "vpn", "label": "VPN 안내", "text": "※ VPN도 중단됩니다."}
    r = client.post("/api/catalog/rows", json={"situation_id": sid, "label": "비고", "token": "apply", "is_optional": True})
    assert r.status_code == 201
    assert client.get("/api/catalog").get_json()["notice"]["sits"]["maint"]["rows"][-1] == {"l": "비고", "tok": "apply", "opt": 1}
    bad = client.put(f"/api/catalog/situations/{sid}/fields", json={"fields": [{"k": "a b", "l": "x"}]})
    assert bad.status_code == 400
    fields = [{"k": "nTitle", "l": "점검 시스템"}, {"k": "apply", "l": "비고"}]
    assert client.put(f"/api/catalog/situations/{sid}/fields", json={"fields": fields}).status_code == 200
    assert client.get("/api/catalog").get_json()["notice"]["sits"]["maint"]["fields"] == fields
    eid = Situation.query.filter_by(code="delay").first().id
    assert client.put(f"/api/catalog/situations/{eid}/fields", json={"fields": ["oldDate", "nope"]}).status_code == 400
