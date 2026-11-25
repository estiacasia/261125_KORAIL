"""서버 렌더링 엔진 — static/js/engine.js 와 같은 규칙 (같은 입력 → 같은 결과).

보안: 템플릿은 직접 구현한 토큰 치환({name})만 사용하며 Jinja2로 렌더링하지 않는다.
"""
import html as _html
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DOW = "일월화수목금토"
LIST_PREFIX = {"board": "  - ", "slack": "    ◦ ", "kakao": "   · "}
TOKEN_RE = re.compile(r"\{(\w+)\}", re.ASCII)
BULLET_RE = re.compile(r"^\s*[-•·◦*▶■]\s*")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
INT_RE = re.compile(r"^\s*([+-]?\d+)")


def esc(s):
    return _html.escape(str(s), quote=True).replace("&#x27;", "&#39;")


def _s(v):
    return "" if v is None else (v if isinstance(v, str) else str(v))


def _to_int(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    m = INT_RE.match(_s(v))
    return int(m.group(1)) if m else 0


def pd(v):
    v = _s(v)
    if not DATE_RE.match(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _dow(d):
    return DOW[(d.weekday() + 1) % 7]


def fD(v):
    d = pd(v)
    return f"{d.month}월 {d.day}일({_dow(d)})" if d else ""


def fT(v):
    m = TIME_RE.match(_s(v))
    if not m:
        return ""
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return ""
    return f"{'오전' if h < 12 else '오후'} {h % 12 or 12}시" + (f" {mi}분" if mi else "")


def fDT(d, t):
    return " ".join(x for x in (fD(d), fT(t)) if x)


def default_state():
    return {
        "mode": "email", "sit": {"email": "schedule", "notice": "internal"}, "aud": "ext", "tone": "formal", "fmt": "board",
        "f": {}, "chips": {}, "tg": {"attach.email": False, "attach.notice": False, "due": False, "sig": False},
        "v": {"subj": 0, "greet": 0, "intro": 0, "core": 0, "close": 0},
    }


def normalize(s):
    b = default_state()
    s = s or {}
    out = {**b, **s}
    out["sit"] = {**b["sit"], **(s.get("sit") or {})}
    out["f"] = dict(s.get("f") or {})
    out["tg"] = {**b["tg"], **(s.get("tg") or {})}
    out["v"] = {k: _to_int(v) for k, v in {**b["v"], **(s.get("v") or {})}.items()}
    out["chips"] = dict(s.get("chips") or {})
    return out


class _Ctx:
    def __init__(self, D, state, sig, month=None, hot=None):
        self.D = D
        self.st = normalize(state)
        self.sig = sig or {}
        self.month = month or datetime.now(ZoneInfo("Asia/Seoul")).month
        self.hot = hot

    # --- helpers
    def sit_key(self):
        return self.st["sit"][self.st["mode"]]

    def S(self):
        return self.D[self.st["mode"]]["sits"][self.sit_key()]

    def chips_on(self):
        c = self.st["chips"].get(self.st["mode"] + "." + self.sit_key())
        if isinstance(c, list):
            return c
        return [x["id"] for x in self.S()["chips"] if x.get("on")]

    def pick(self, arr, k):
        n = len(arr)
        if not n:
            return ""
        return arr[(self.st["v"].get(k) or 0) % n]

    def filled(self):
        c = self.st["f"].get("cands")
        c = c if isinstance(c, list) else []
        return [x for x in c if isinstance(x, dict) and _s(x.get("d"))]

    def f(self, k):
        return _s(self.st["f"].get(k))

    def nf(self, x):
        return self.f(self.sit_key() + "." + x).strip()

    def nlab(self, x):
        for d in self.S().get("fields") or []:
            if isinstance(d, dict) and d.get("k") == x:
                return d.get("l")
        return x

    @staticmethod
    def V(v, l, g):
        return {"t": v, "kind": "v", "g": g} if v else {"t": f"[{l}]", "kind": "p"}

    def season(self):
        return _s(self.D["season"].get(str(self.month)))

    def sg(self, x):
        return _s(self.sig.get(x)).strip()

    def sig_lines(self):
        sg = self.sg
        return [
            " ".join(x for x in (sg("name"), sg("title")) if x),
            " | ".join(x for x in (sg("dept"), sg("company")) if x),
            "  ·  ".join(x for x in (sg("phone") and "T. " + sg("phone"), sg("email") and "E. " + sg("email")) if x),
        ]

    def sig_block(self):
        L = [f"{{sig{i + 1}}}" for i, x in enumerate(self.sig_lines()) if x]
        return "────────────\n" + ("\n".join(L) if L else "{sig0}")

    def n_when(self):
        w, d1, d2 = self.S().get("when"), self.nf("d1"), self.nf("d2")
        if w == "range":
            s = fDT(d1, self.nf("t1"))
            e = fDT(d2, self.nf("t2")) if d2 and d2 != d1 else fT(self.nf("t2"))
            return f"{s} ~ {e}" if s and e else s
        if w == "days":
            if not d1:
                return ""
            p1, p2 = pd(d1), pd(d2)
            if d2 and d2 > d1 and p1 and p2:
                n = (p2 - p1).days + 1
                return f"{fD(d1)} ~ {fD(d2)} ({n}일간)"
            return fD(d1)
        return fDT(d1, self.nf("t1"))

    def resume(self):
        b = pd(self.nf("d2") or self.nf("d1"))
        if not b:
            return ""
        d = b + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return fD(d.isoformat())

    # --- tokens
    def R(self, k):
        st, V = self.st, self.V
        em = st["mode"] == "email"
        if k == "to":
            v = self.f("to").strip()
            if v:
                return {"t": v, "kind": "v", "g": "to"}
            a = self.D["aud"].get(st["aud"])
            return {"t": a["defTo"] if a else "", "kind": "n"}
        if k == "proj":
            return V(self.f("proj").strip(), "프로젝트명", "proj")
        if k == "memo":
            return V(self.f("memo." + self.sit_key()).strip(), self.S().get("memoName"), "memo")
        if k == "cands":
            c = self.filled()
            if not c:
                return V("", "후보 일정", None)
            if len(c) == 1:
                t = fDT(c[0].get("d"), c[0].get("t"))
            else:
                t = "\n".join(f"{i + 1}) {fDT(x.get('d'), x.get('t'))}" for i, x in enumerate(c))
            return {"t": t, "kind": "v", "g": "cands"}
        if k == "oldDate":
            return V(fD(self.f("oldDate")), "기존 마감일", "oldDate")
        if k == "newDate":
            return V(fD(self.f("newDate")), "변경 예정일", "newDate")
        if k == "when":
            return V(fDT(self.f("mDate"), self.f("mTime")), "미팅 일시", "when")
        if k == "place":
            return V(self.f("place").strip(), "장소", "place") if em else V(self.nf("place"), self.nlab("place"), "place")
        if k == "link":
            return V(self.f("link").strip(), "화상회의 링크", "link")
        if k == "files":
            return V(self.f("files." + st["mode"]).strip(), "파일명", "files")
        if k == "due":
            return V(fD(self.f("due")), "회신 기한", "due")
        if k == "sender":
            n = self.sg("name")
            if not n:
                return V("", "보내는 사람", None)
            t = n if st["aud"] == "team" else " ".join(x for x in (self.sg("dept"), n) if x)
            return {"t": t, "kind": "v", "g": "sig"}
        if k == "issuer":
            return V(self.sg("dept") or self.sg("name"), "발신 부서", "sig")
        if k == "sig0":
            return V("", "서명 정보 입력", None)
        if k in ("sig1", "sig2", "sig3"):
            t = self.sig_lines()[int(k[3]) - 1]
            return {"t": t, "kind": "v", "g": "sig"} if t else {"t": "", "kind": "n"}
        if k == "nWhen":
            return V(self.n_when(), self.S().get("whenLabel"), "nWhen")
        if k == "applyDue":
            return V(fD(self.nf("applyDue")), "신청 마감", "applyDue")
        if k == "resume":
            return V(self.resume(), "업무 재개일", "nWhen")
        if k == "content":
            pre = LIST_PREFIX.get(st["fmt"], LIST_PREFIX["board"])
            L = [BULLET_RE.sub("", s, count=1).strip() for s in self.nf("content").split("\n")]
            L = [x for x in L if x]
            if L:
                return {"t": "\n".join(pre + x for x in L), "kind": "v", "g": "content"}
            return {"t": pre + f"[{self.nlab('content')}]", "kind": "p"}
        if k in ("nTitle", "target", "apply", "contact"):
            return V(self.nf(k), self.nlab(k), k)
        return None

    def has(self, k):
        r = self.R(k)
        return bool(r) and r["kind"] == "v"

    def fill(self, tpl, html=False):
        tpl = _s(tpl).replace("%s%", self.season())
        out = []
        for i, p in enumerate(TOKEN_RE.split(tpl)):
            if i % 2 == 0:
                out.append(esc(p) if html else p)
                continue
            r = self.R(p)
            if r is None:
                out.append(esc("{" + p + "}") if html else "{" + p + "}")
            elif not html:
                out.append(r["t"])
            elif r["kind"] == "v":
                cls = ' class="hot"' if r["g"] == self.hot else ""
                out.append(f'<mark data-g="{esc(r["g"])}"{cls}>{esc(r["t"])}</mark>')
            elif r["kind"] == "p":
                out.append(f'<span class="ph">{esc(r["t"])}</span>')
            else:
                out.append(esc(r["t"]))
        return "".join(out)

    # --- builders
    def build_email(self):
        s, st, D = self.S(), self.st, self.D
        t, a, on, P = st["tone"], st["aud"], self.chips_on(), []
        subj = self.pick(s["subj"][t], "subj")
        P.append(self.pick(D["greet"][a][t], "greet"))
        P.append(self.pick(s["intro"][t], "intro"))
        src = s["coreMulti"] if s.get("coreMulti") and len(self.filled()) > 1 else s["core"]
        core = self.pick(src[t], "core")
        if self.sit_key() == "remind":
            L, hl = ["· 일시: {when}"], self.has("link")
            if self.has("place") or not hl:
                L.append("· 장소: {place}")
            if hl:
                L.append("· 화상회의: {link}")
            core += "\n" + "\n".join(L)
        P.append(core)
        if s.get("memoMode") == "opt" and self.has("memo"):
            P.append("{memo}")
        cs = [_s(c.get(t)) for c in s["chips"] if c["id"] in on]
        P.extend(x for x in cs if "\n" in x)
        one = [x for x in cs if "\n" not in x]
        if one:
            P.append("\n".join(one))
        if st["tg"].get("attach.email"):
            P.append(_s(D["opt"]["attach"][t]) + ("\n" + _s(D["opt"]["files"]) if self.has("files") else ""))
        if st["tg"].get("due"):
            P.append(_s(D["opt"]["due"][t]))
        P.append("\n".join(x for x in (self.pick(s["closeLead"][t], "close"), self.pick(D["close"][a][t], "close")) if x))
        if st["tg"].get("sig"):
            P.append(self.sig_block())
        return {"s": subj, "b": "\n\n".join(x for x in P if x)}

    def build_notice(self):
        s, st, N = self.S(), self.st, self.D["notice"]
        t, fm, on = st["tone"], st["fmt"], self.chips_on()
        subj = self.pick(s["subj"], "subj")
        greet, intro, lead = self.pick(N["greet"][t], "greet"), self.pick(s["intro"][t], "intro"), self.pick(N["lead"][t], "core")
        rows = []
        for r in s["rows"]:
            if r.get("opt") and not self.has(r["tok"]):
                continue
            tk = "{" + r["tok"] + "}"
            if fm == "slack":
                rows.append(f"• *{r['l']}*\n{tk}" if r.get("list") else f"• *{r['l']}*: {tk}")
            elif fm == "kakao":
                rows.append(f"▶ {r['l']}\n{tk}" if r.get("list") else f"▶ {r['l']}: {tk}")
            else:
                rows.append(f"■ {r['l']}\n{tk}" if r.get("list") else f"■ {r['l']}: {tk}")
        rows = "\n".join(rows)
        notes = [_s(c.get("text")) for c in s["chips"] if c["id"] in on]
        if st["tg"].get("attach.notice"):
            notes.append(_s(self.D["opt"]["nFiles"]) if self.has("files") else _s(self.D["opt"]["nAttach"][t]))
        close = " ".join(x for x in (self.pick(s["closeLead"][t], "close"), self.pick(N["close"][t], "close")) if x)
        if fm == "slack":
            P = ["*" + subj + "*", greet + " " + intro, rows, "\n".join("> " + n for n in notes), close]
        elif fm == "kakao":
            P = ["📢 " + subj, greet + "\n" + intro, lead + "\n" + rows, "\n".join(notes), close, "- {issuer} -"]
        else:
            P = [greet + "\n" + intro, lead + "\n\n" + rows, "\n".join(notes), close, "{issuer} 드림",
                 self.sig_block() if st["tg"].get("sig") else ""]
        return {"s": subj, "b": "\n\n".join(x for x in P if x)}

    def tag(self):
        st, D = self.st, self.D
        t = "격식" if st["tone"] == "formal" else "실무"
        if st["mode"] == "email":
            return f"{self.S()['name']} · {D['aud'][st['aud']]['name']} · {t}"
        return f"공지 · {self.S()['name']} · {D['notice']['fmtName'][st['fmt']]} · {t}"


def render(catalog, state, sig=None, month=None, hot=None):
    """Return dict(subject, body, subjectHtml, bodyHtml, tag)."""
    c = _Ctx(catalog, state, sig, month, hot)
    o = c.build_email() if c.st["mode"] == "email" else c.build_notice()
    return {
        "subject": c.fill(o["s"]), "body": c.fill(o["b"]),
        "subjectHtml": c.fill(o["s"], True), "bodyHtml": c.fill(o["b"], True),
        "tag": c.tag(),
    }


def validate_state(catalog, state):
    """구조 검증. 문제 없으면 None, 있으면 (message, field)."""
    if not isinstance(state, dict):
        return ("state가 올바르지 않습니다.", None)
    st = normalize(state)
    if st["mode"] not in ("email", "notice"):
        return ("작성 모드가 올바르지 않습니다.", "mode")
    if st["sit"].get(st["mode"]) not in catalog[st["mode"]]["sits"]:
        return ("상황이 올바르지 않습니다.", "sit")
    if st["aud"] not in catalog["aud"]:
        return ("수신 대상이 올바르지 않습니다.", "aud")
    if st["tone"] not in ("formal", "brief"):
        return ("톤이 올바르지 않습니다.", "tone")
    if st["fmt"] not in catalog["notice"]["fmtName"]:
        return ("게시 채널이 올바르지 않습니다.", "fmt")
    if not isinstance(state.get("f", {}), dict) or not isinstance(state.get("chips", {}), dict):
        return ("입력값 형식이 올바르지 않습니다.", "f")
    for k, v in (state.get("chips") or {}).items():
        if v is not None and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            return ("칩 선택값이 올바르지 않습니다.", "chips." + k)
    return None
