import copy
import json
import os
import shutil
import subprocess

import pytest

from app.renderer import render
from conftest import ROOT

CASES = json.load(open(os.path.join(ROOT, "tests", "fixtures", "render_cases.json"), encoding="utf-8"))
SIG = {"name": "이지은", "title": "매니저", "dept": "마케팅팀", "company": "", "phone": "010-1234-5678", "email": "jieun@example.com"}
KEYS = ("subject", "body", "subjectHtml", "bodyHtml")


def st(mode="email", sit="schedule", **kw):
    s = {"mode": mode, "sit": {"email": "schedule", "notice": "internal"}, "aud": "ext", "tone": "formal", "fmt": "board",
         "f": {}, "chips": {}, "tg": {"attach.email": False, "attach.notice": False, "due": False, "sig": False},
         "v": {"subj": 0, "greet": 0, "intro": 0, "core": 0, "close": 0}}
    s["sit"][mode] = sit
    s.update(kw)
    return s


def test_fixture_count():
    assert len(CASES) >= 30


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_python(seed, case):
    r = render(seed, case["state"], case["sig"], month=case["month"], hot=case["hot"])
    for k in KEYS:
        assert r[k] == case["expected"][k], k


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js가 없어 JS 엔진 비교를 건너뜁니다")
def test_fixture_js_matches_python():
    out = subprocess.run(["node", os.path.join("tests", "run_engine.mjs"), "--json"], cwd=ROOT, capture_output=True, check=True)
    js = json.loads(out.stdout.decode("utf-8"))
    assert len(js) == len(CASES)
    for r, c in zip(js, CASES):
        for k in KEYS:
            assert r[k] == c["expected"][k], f"{c['name']} {k}"


@pytest.mark.parametrize("sit", ["schedule", "request", "delay", "remind", "coop"])
@pytest.mark.parametrize("tone", ["formal", "brief"])
@pytest.mark.parametrize("aud", ["ext", "dept", "team"])
def test_email_all_combinations(seed, sit, tone, aud):
    r = render(seed, st("email", sit, tone=tone, aud=aud, f={"to": "홍길동님", "proj": "P"}), SIG, month=5)
    assert r["subject"] and r["body"]
    assert "홍길동님" in r["body"]
    sender = "이지은" if aud == "team" else "마케팅팀 이지은"
    assert sender in r["body"]


@pytest.mark.parametrize("sit", ["internal", "recruit", "maint", "holiday"])
@pytest.mark.parametrize("tone", ["formal", "brief"])
@pytest.mark.parametrize("fmt", ["board", "slack", "kakao"])
def test_notice_all_combinations(seed, sit, tone, fmt):
    r = render(seed, st("notice", sit, tone=tone, fmt=fmt, f={f"{sit}.nTitle": "제목", f"{sit}.content": "가\n나"}), SIG)
    b = r["body"]
    if fmt == "slack":
        assert b.startswith("*") and "    ◦ 가" in b
    elif fmt == "kakao":
        assert b.startswith("📢 ") and "   · 가" in b and b.endswith("- 마케팅팀 -")
    else:
        assert "  - 가" in b and "마케팅팀 드림" in b


def test_empty_placeholders(seed):
    r = render(seed, st("email", "delay"), {})
    assert "담당자님께" in r["body"]
    for p in ("[프로젝트명]", "[기존 마감일]", "[변경 예정일]", "[보내는 사람]", "[지연 사유]"):
        assert p in r["body"] or p in r["subject"]
    assert '<span class="ph">[프로젝트명]</span>' in r["subjectHtml"]
    team = render(seed, st("email", "delay", aud="team"), {})
    assert "팀원 여러분" in team["body"]


def test_cands_0_1_3(seed):
    def body(cands):
        return render(seed, st("email", "schedule", f={"cands": cands}), SIG)["body"]
    assert "[후보 일정]" in body([])
    one = body([{"d": "2026-12-03", "t": "14:00"}])
    assert "12월 3일(목) 오후 2시에" in one and "1)" not in one
    three = body([{"d": "2026-12-03", "t": "09:30"}, {"d": "2026-12-04", "t": ""}, {"d": "2026-12-07", "t": "16:00"}])
    assert "1) 12월 3일(목) 오전 9시 30분\n2) 12월 4일(금)\n3) 12월 7일(월) 오후 4시" in three


def test_days_and_resume_weekend(seed):
    f = {"holiday.d1": "2026-12-24", "holiday.d2": "2026-12-26", "holiday.nTitle": "연말"}
    b = render(seed, st("notice", "holiday", f=f), SIG)["body"]
    assert "12월 24일(목) ~ 12월 26일(토) (3일간)" in b
    assert "12월 28일(월)부터 정상 업무가 재개됩니다." in b  # 토·일 건너뜀
    f = {"holiday.d1": "2026-12-16", "holiday.d2": ""}
    b = render(seed, st("notice", "holiday", f=f), SIG)["body"]
    assert "12월 17일(목)부터" in b


def test_maint_range(seed):
    f = {"maint.d1": "2026-12-06", "maint.t1": "22:00", "maint.d2": "2026-12-07", "maint.t2": "06:00"}
    b = render(seed, st("notice", "maint", f=f), SIG)["body"]
    assert "12월 6일(일) 오후 10시 ~ 12월 7일(월) 오전 6시" in b
    f["maint.d2"] = "2026-12-06"
    f["maint.t2"] = "23:30"
    b = render(seed, st("notice", "maint", f=f), SIG)["body"]
    assert "12월 6일(일) 오후 10시 ~ 오후 11시 30분" in b


@pytest.mark.parametrize("month", range(1, 13))
def test_season_by_month(seed, month):
    s = st("email", "schedule", v={"subj": 0, "greet": 0, "intro": 0, "core": 0, "close": 0})
    b = render(seed, s, SIG, month=month)["body"]
    assert seed["season"][str(month)] in b
    assert "%s%" not in b


def test_chip_on_off(seed):
    on = render(seed, st("email", "delay", chips={"email.delay": ["prevent"]}), SIG)["body"]
    off = render(seed, st("email", "delay", chips={"email.delay": []}), SIG)["body"]
    sentence = seed["email"]["sits"]["delay"]["chips"][2]["formal"]
    assert sentence in on and sentence not in off
    default = render(seed, st("email", "delay"), SIG)["body"]
    assert "▶ 변경 완료 예정일" in default  # default_on 칩


def test_attach_mode_separated(seed):
    f = {"files.email": "메일.pdf", "files.notice": "공지.pdf"}
    e = render(seed, st("email", "coop", f=f, tg={"attach.email": True, "attach.notice": False}), SIG)["body"]
    assert "· 첨부: 메일.pdf" in e and "공지.pdf" not in e
    n = render(seed, st("notice", "maint", f=f, tg={"attach.email": True, "attach.notice": False}), SIG)["body"]
    assert "첨부" not in n
    n = render(seed, st("notice", "maint", f=f, tg={"attach.email": False, "attach.notice": True}), SIG)["body"]
    assert "※ 첨부 파일: 공지.pdf" in n


def test_injection_is_literal(seed):
    f = {"to": "<script>alert(1)</script>", "proj": "{{7*7}}", "memo.request": "{proj} <img src=x onerror=alert(1)>"}
    r = render(seed, st("email", "request", f=f), SIG)
    assert "{{7*7}}" in r["subject"] and "49" not in r["subject"]
    assert "<script>alert(1)</script>" in r["body"]
    assert "{proj} <img" in r["body"]  # 입력값 속 토큰은 다시 치환하지 않음
    assert "<script>" not in r["bodyHtml"] and "<img" not in r["bodyHtml"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in r["bodyHtml"]


def test_unknown_token_kept(seed):
    cat = copy.deepcopy(seed)
    cat["email"]["sits"]["coop"]["subj"]["formal"] = ["{nope} {proj}"]
    r = render(cat, st("email", "coop", f={"proj": "P"}), SIG)
    assert r["subject"] == "{nope} P"


def test_shuffle_changes_text(seed):
    a = render(seed, st("email", "delay", f={"proj": "P"}), SIG)
    b = render(seed, st("email", "delay", f={"proj": "P"}, v={"subj": 1, "greet": 1, "intro": 1, "core": 1, "close": 1}), SIG)
    assert a["subject"] != b["subject"] and a["body"] != b["body"]
