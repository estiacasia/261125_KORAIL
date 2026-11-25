"""입력값 검증 (작업 지시서 1-9)."""
import re

from .renderer import DATE_RE, TIME_RE, pd

URL_RE = re.compile(r"^https?://\S+$", re.I)
JOSA_RE = re.compile(r"\}\s*(은|는|이|가|을|를|과|와)\b")
KNOWN_TOKENS = {
    "to", "sender", "proj", "memo", "cands", "oldDate", "newDate", "due", "when", "place", "link", "files", "issuer",
    "sig0", "sig1", "sig2", "sig3", "nTitle", "target", "apply", "contact", "nWhen", "applyDue", "resume", "content",
}
TOKEN_RE = re.compile(r"\{(\w+)\}", re.ASCII)

LIMIT_SINGLE = 200
LIMIT_MULTI = 2000


class ValidationError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def field_types(catalog):
    types = {}
    for k, d in catalog.get("emailFields", {}).items():
        types[k] = d.get("type", "text")
    for code, s in catalog["notice"]["sits"].items():
        for d in s.get("fields", []):
            types[f"{code}.{d['k']}"] = d.get("type", "text")
    return types


def _check_date(v, field):
    if v and (not DATE_RE.match(v) or pd(v) is None):
        raise ValidationError("날짜는 YYYY-MM-DD 형식이어야 합니다.", field)


def _check_time(v, field):
    if v:
        m = TIME_RE.match(v)
        if not m or len(v) != 5 or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValidationError("시간은 HH:MM 형식이어야 합니다.", field)


def _limit(v, n, field, label):
    if len(v) > n:
        raise ValidationError(f"{label}은(는) {n:,}자 이하로 입력해 주세요.", field)


def validate_inputs(catalog, f):
    if not isinstance(f, dict):
        raise ValidationError("입력값 형식이 올바르지 않습니다.", "f")
    types = field_types(catalog)
    for k, v in f.items():
        if k == "cands":
            if not isinstance(v, list) or len(v) > 3:
                raise ValidationError("후보 일정은 최대 3개입니다.", "cands")
            for i, c in enumerate(v):
                if not isinstance(c, dict):
                    raise ValidationError("후보 일정 형식이 올바르지 않습니다.", "cands")
                _check_date(str(c.get("d") or ""), f"cands.{i}.d")
                _check_time(str(c.get("t") or ""), f"cands.{i}.t")
            continue
        if v is None:
            continue
        if not isinstance(v, str):
            raise ValidationError("입력값은 문자열이어야 합니다.", k)
        t = types.get(k)
        if k == "to":
            _limit(v, 50, k, "수신자명")
        elif k == "proj":
            _limit(v, 100, k, "프로젝트명")
        elif k.endswith(".nTitle"):
            _limit(v, 100, k, "공지 제목")
        elif k.startswith("files."):
            _limit(v, 200, k, "파일명")
        elif k == "due":
            _check_date(v, k)
        elif k.startswith("memo.") or t == "textarea":
            _limit(v, LIMIT_MULTI, k, "여러 줄 입력")
        elif t == "date":
            _check_date(v, k)
        elif t == "time":
            _check_time(v, k)
        elif t == "url":
            _limit(v, LIMIT_SINGLE, k, "링크")
            if v.strip() and not URL_RE.match(v.strip()):
                raise ValidationError("링크는 http:// 또는 https:// 로 시작해야 합니다.", k)
        elif t is not None:
            _limit(v, LIMIT_SINGLE, k, "입력값")
        else:
            _limit(v, LIMIT_MULTI, k, "입력값")


def validate_sig(sig):
    if sig is None:
        return
    if not isinstance(sig, dict):
        raise ValidationError("서명 형식이 올바르지 않습니다.", "sig")
    for k, v in sig.items():
        if v is not None and (not isinstance(v, str) or len(v) > 100):
            raise ValidationError("서명 항목은 100자 이하 문자열이어야 합니다.", "sig." + k)


def text_warnings(text):
    """문구 관리 저장 시 경고 (저장은 막지 않음)."""
    w = []
    for m in JOSA_RE.finditer(text or ""):
        w.append(f"조사 규칙: 토큰 바로 뒤 '{m.group(1)}' — 받침에 따라 어색해질 수 있습니다. '께', '입니다', '관련' 등으로 바꿔 주세요.")
    for tok in TOKEN_RE.findall(text or ""):
        if tok not in KNOWN_TOKENS:
            w.append(f"정의되지 않은 토큰 {{{tok}}} — 원문 그대로 출력됩니다.")
    return w
