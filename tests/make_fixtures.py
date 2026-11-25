"""tests/fixtures/render_cases.json 생성기.

    python tests/make_fixtures.py

케이스 입력을 만들고 Python 렌더러 결과를 expected로 저장한다.
JS 엔진(tests/run_engine.mjs)과 Python 렌더러가 모두 이 expected와 일치해야 한다.
"""
import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.renderer import render  # noqa: E402

CAT = json.load(open(os.path.join(ROOT, "data", "seed_catalog.json"), encoding="utf-8"))
SAMPLE = json.loads(subprocess.check_output(
    ["node", "-e", "process.stdout.write(JSON.stringify(require('./app/static/js/engine.js').SAMPLE))"], cwd=ROOT).decode("utf-8"))
SIG = {"name": "이지은", "title": "매니저", "dept": "마케팅팀", "company": "", "phone": "010-1234-5678", "email": "jieun@example.com"}
TG = {"attach.email": True, "attach.notice": False, "due": False, "sig": True}
V0 = {"subj": 0, "greet": 0, "intro": 0, "core": 0, "close": 0}


def state(mode, sit, **kw):
    s = {"mode": mode, "sit": {"email": "schedule", "notice": "internal"}, "aud": "ext", "tone": "formal", "fmt": "board",
         "f": copy.deepcopy(SAMPLE), "chips": {}, "tg": dict(TG), "v": dict(V0)}
    s["sit"][mode] = sit
    for k, v in kw.items():
        s[k] = v
    return s


cases = []


def add(name, st, sig=SIG, month=11, hot=None):
    cases.append({"name": name, "state": st, "sig": sig, "month": month, "hot": hot})


# 1) 이메일 5상황 × 2톤 × 3대상
for sit in CAT["email"]["order"]:
    for tone in ("formal", "brief"):
        for aud in ("ext", "dept", "team"):
            add(f"email.{sit}.{tone}.{aud}", state("email", sit, tone=tone, aud=aud))
# 2) 공지 4상황 × 2톤 × 3채널
for sit in CAT["notice"]["order"]:
    for tone in ("formal", "brief"):
        for fmt in ("board", "slack", "kakao"):
            add(f"notice.{sit}.{tone}.{fmt}", state("notice", sit, tone=tone, fmt=fmt, tg={**TG, "attach.notice": fmt == "board"}))
# 3) 빈 값 placeholder (서명 없음)
for sit in CAT["email"]["order"]:
    add(f"empty.email.{sit}", state("email", sit, f={}, tg={"attach.email": True, "due": True, "sig": True}), sig={})
for sit in CAT["notice"]["order"]:
    for fmt in ("board", "kakao"):
        add(f"empty.notice.{sit}.{fmt}", state("notice", sit, f={}, fmt=fmt, tg={"attach.notice": True, "sig": True}), sig={})
# 4) 셔플 seed
for i, v in enumerate([{"subj": 1, "greet": 2, "intro": 3, "core": 4, "close": 5}, {"subj": 7, "greet": 9, "intro": 11, "core": 2, "close": 13}, {"subj": -1, "greet": -5, "intro": 0, "core": 0, "close": -2}]):
    add(f"shuffle.email.delay.{i}", state("email", "delay", v=v, aud="dept"))
    add(f"shuffle.notice.recruit.{i}", state("notice", "recruit", v=v, fmt="slack"))
# 5) 칩 조합
for sit in CAT["email"]["order"]:
    ids = [c["id"] for c in CAT["email"]["sits"][sit]["chips"]]
    add(f"chips.all.email.{sit}", state("email", sit, chips={f"email.{sit}": ids}))
    add(f"chips.none.email.{sit}", state("email", sit, chips={f"email.{sit}": []}, tone="brief"))
for sit in CAT["notice"]["order"]:
    ids = [c["id"] for c in CAT["notice"]["sits"][sit]["chips"]]
    add(f"chips.all.notice.{sit}", state("notice", sit, chips={f"notice.{sit}": ids}, fmt="kakao"))
# 6) 후보 일정 0/1/3
for n, cands in (("0", []), ("1", [{"d": "2026-12-03", "t": "09:30"}]),
                 ("3", [{"d": "2026-12-03", "t": "14:00"}, {"d": "2026-12-04", "t": ""}, {"d": "2026-12-07", "t": "16:15"}]),
                 ("timeonly", [{"d": "", "t": "10:00"}])):
    s = state("email", "schedule")
    s["f"]["cands"] = cands
    s["f"]["memo.schedule"] = "1차 시안 리뷰가 주요 안건입니다."
    add(f"cands.{n}", s)
# 7) 미팅 리마인드 장소·링크
for name, place, link in (("place", "본사 3층", ""), ("link", "", "https://zoom.us/j/123"), ("both", "본사 3층", "https://teams.microsoft.com/l/x"), ("none", "", "")):
    s = state("email", "remind", tone="brief")
    s["f"]["place"], s["f"]["link"] = place, link
    add(f"remind.{name}", s)
# 8) 기간·재개일
for name, d1, d2 in (("same", "2026-12-18", "2026-12-18"), ("fri_to_sat", "2026-12-24", "2026-12-26"), ("multi", "2026-12-30", "2027-01-02"), ("reverse", "2026-12-20", "2026-12-18")):
    s = state("notice", "holiday")
    s["f"]["holiday.d1"], s["f"]["holiday.d2"] = d1, d2
    add(f"holiday.{name}", s)
for name, d2, t2 in (("sameday", "2026-12-06", "23:30"), ("nextday", "2026-12-07", "06:00"), ("noend", "", "")):
    s = state("notice", "maint", fmt="slack")
    s["f"]["maint.d2"], s["f"]["maint.t2"] = d2, t2
    add(f"maint.{name}", s)
# 9) 계절 인사 월별
for m in range(1, 13):
    add(f"season.{m}", state("email", "schedule", v={**V0, "greet": 0}), month=m)
# 10) 보안 입력 · 회신 기한 · 첨부 모드 분리 · 하이라이트
s = state("email", "request", tg={**TG, "due": True})
s["f"].update({"to": "<img src=x onerror=alert(1)>", "proj": "{{7*7}}", "memo.request": "<script>alert('x')</script>\n- {proj} & \"따옴표\""})
add("security.email", s, hot="proj")
s = state("notice", "internal", tg={**TG, "attach.notice": True})
s["f"].update({"internal.nTitle": "{{ config }}", "internal.content": "- <b>굵게</b>\n• 항목2\n■ 항목3\n\n", "files.notice": "a.pdf, b.xlsx"})
add("security.notice", s, hot="content")
s = state("email", "coop", tg={"attach.email": True, "attach.notice": True, "due": False, "sig": False})
s["f"]["files.email"] = ""
add("attach.email.nofile", s)
s = state("notice", "maint", tg={"attach.email": True, "attach.notice": False, "sig": False})
add("attach.notice.off", s)
add("unknown.token", state("email", "coop", f={**SAMPLE, "proj": "{unknown} {to}"}))

for c in cases:
    c["expected"] = render(CAT, c["state"], c["sig"], month=c["month"], hot=c["hot"])
    c["expected"].pop("tag", None)

out = os.path.join(ROOT, "tests", "fixtures", "render_cases.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(cases, f, ensure_ascii=False, indent=1)
print(f"{len(cases)} cases → {out}")
