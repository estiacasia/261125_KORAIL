import time

from app import create_app
from app.models import Contact, History, Project
from conftest import base_state


def test_render(client):
    r = client.post("/api/render", json={"state": base_state()})
    assert r.status_code == 200
    d = r.get_json()
    assert d["subject"].startswith("[2027 브랜드 리뉴얼]")
    assert "12월 4일(금)" in d["body"] and "12월 11일(금)" in d["body"]
    assert "마케팅팀 이지은" in d["body"]  # 설정의 서명 사용


def test_render_uses_given_sig(client):
    r = client.post("/api/render", json={"state": base_state(), "sig": {"name": "박하늘", "dept": "영업팀"}})
    assert "영업팀 박하늘" in r.get_json()["body"]


def test_validation_errors(client):
    def bad(f, field):
        s = base_state()
        s["f"].update(f)
        r = client.post("/api/render", json={"state": s})
        assert r.status_code == 400, f
        err = r.get_json()["error"]
        assert err["code"] == "VALIDATION_ERROR" and err["field"] == field
    bad({"to": "가" * 51}, "to")
    bad({"proj": "x" * 101}, "proj")
    bad({"oldDate": "2026/12/04"}, "oldDate")
    bad({"oldDate": "2026-02-30"}, "oldDate")
    bad({"mTime": "25:00"}, "mTime")
    bad({"link": "javascript:alert(1)"}, "link")
    bad({"memo.delay": "x" * 2001}, "memo.delay")
    bad({"files.email": "x" * 201}, "files.email")
    bad({"maint.d1": "tomorrow"}, "maint.d1")
    bad({"cands": [{"d": "x", "t": ""}]}, "cands.0.d")
    r = client.post("/api/render", json={"state": base_state(mode="fax")})
    assert r.status_code == 400 and r.get_json()["error"]["field"] == "mode"
    r = client.post("/api/render", json={"state": base_state(sit={"email": "nope"})})
    assert r.status_code == 400


def test_history_save_dedup_and_edited(client):
    s = base_state()
    r = client.post("/api/history", json={"state": s, "action": "copy"})
    assert r.status_code == 201
    r2 = client.post("/api/history", json={"state": s, "action": "mailto"})
    assert r2.status_code == 200 and r2.get_json()["duplicate"] is True
    assert History.query.count() == 1
    r3 = client.post("/api/history", json={"state": s, "action": "copy", "edited": {"subject": "수정 제목", "body": "수정 본문"}})
    assert r3.status_code == 201
    h = client.get(f"/api/history/{r3.get_json()['id']}").get_json()
    assert h["is_edited"] and h["subject"] == "수정 제목" and h["body"] == "수정 본문"
    assert h["snapshot"]["sit"] == {"email": "delay"} and h["snapshot"]["chips"] == {"email.delay": ["cause", "emph"]}


def test_history_list_search_fav_delete(client):
    for i, proj in enumerate(["알파", "베타", "감마"]):
        s = base_state()
        s["f"]["proj"] = proj
        client.post("/api/history", json={"state": s, "action": "copy"})
    items = client.get("/api/history?limit=5").get_json()["items"]
    assert [x["project_name"] for x in items] == ["감마", "베타", "알파"]
    assert client.get("/api/history?q=베타").get_json()["total"] == 1
    hid = items[0]["id"]
    assert client.patch(f"/api/history/{hid}", json={"is_favorite": True}).get_json()["is_favorite"]
    assert client.get("/api/history?fav=1").get_json()["total"] == 1
    assert client.delete(f"/api/history/{hid}").status_code == 200
    assert client.get(f"/api/history/{hid}").status_code == 404
    assert client.get("/history?q=알파").status_code == 200
    assert client.get(f"/history/{items[1]['id']}").status_code == 200


def test_history_updates_usage(client, app):
    client.post("/api/contacts", json={"display_name": "김민수 팀장님", "email": "kim@a.com", "default_audience": "ext"})
    client.post("/api/projects", json={"name": "2027 브랜드 리뉴얼"})
    client.post("/api/history", json={"state": base_state(), "action": "copy"})
    assert Contact.query.first().use_count == 1
    assert Project.query.first().use_count == 1


def test_presets_crud_and_limit(client):
    r = client.post("/api/presets", json={"name": "A사 월간", "snapshot": base_state()})
    assert r.status_code == 201
    pid = r.get_json()["id"]
    assert client.get(f"/api/presets/{pid}").get_json()["snapshot"]["sit"]["email"] == "delay"
    assert client.put(f"/api/presets/{pid}", json={"name": "B사", "snapshot": base_state(tone="brief")}).get_json()["name"] == "B사"
    assert client.post("/api/presets", json={"name": "", "snapshot": base_state()}).status_code == 400
    for i in range(22):
        client.post("/api/presets", json={"name": f"p{i}", "snapshot": base_state()})
    assert len(client.get("/api/presets").get_json()["items"]) == 20
    last = client.get("/api/presets").get_json()["items"][0]["id"]
    assert client.delete(f"/api/presets/{last}").status_code == 200
    assert client.get(f"/api/presets/{last}").status_code == 404


def test_contacts_projects(client):
    r = client.post("/api/contacts", json={"display_name": "이영희 과장님", "company": "B사", "email": "lee@b.com", "default_audience": "dept"})
    cid = r.get_json()["id"]
    assert client.get("/api/contacts?q=영희").get_json()["items"][0]["default_audience"] == "dept"
    assert client.put(f"/api/contacts/{cid}", json={"display_name": "이영희 차장님", "default_audience": "zzz"}).status_code == 400
    assert client.put(f"/api/contacts/{cid}", json={"display_name": "이영희 차장님"}).get_json()["display_name"] == "이영희 차장님"
    assert client.delete(f"/api/contacts/{cid}").status_code == 200
    p = client.post("/api/projects", json={"name": "신규"}).get_json()
    assert client.post("/api/projects", json={"name": "신규"}).status_code == 400
    assert client.put(f"/api/projects/{p['id']}", json={"name": "신규", "is_archived": True}).get_json()["is_archived"]
    assert client.get("/api/projects?q=신규").get_json()["items"] == []  # 보관된 프로젝트는 자동완성 제외


def test_settings(client):
    d = client.get("/api/settings").get_json()
    assert d["sig"]["name"] == "이지은" and d["default_mode"] == "email"
    d = client.put("/api/settings", json={"sig": {"name": "박하늘", "company": "(주)테스트"}, "default_tone": "brief"}).get_json()
    assert d["sig"]["name"] == "박하늘" and d["sig"]["dept"] == "마케팅팀" and d["default_tone"] == "brief"
    assert client.put("/api/settings", json={"default_mode": "fax"}).status_code == 400


def test_pages_render(client):
    for url in ("/", "/history", "/contacts", "/catalog", "/settings"):
        assert client.get(url).status_code == 200, url


def test_csrf_enforced(tmp_path, seed):
    app = create_app({"TESTING": True, "SECRET_KEY": "t", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "c.sqlite3").replace("\\", "/")})
    from app.catalog import seed_catalog
    from app.extensions import db
    with app.app_context():
        db.create_all()
        seed_catalog(seed)
        c = app.test_client()
        r = c.post("/api/render", json={"state": base_state()})
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "CSRF_ERROR"
        db.engine.dispose()
