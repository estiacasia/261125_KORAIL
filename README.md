# 이메일·공지문 템플릿 생성기 (Flask)

아티팩트 「이메일·공지문 템플릿 생성기 v2」를 Flask + SQLite 웹앱으로 옮긴 프로젝트입니다.
핵심 키워드만 넣으면 상황·대상·톤에 맞는 비즈니스 메일과 사내 공지(게시판·슬랙·카카오톡)를 바로 만들어 줍니다.

- 미리보기는 브라우저에서 즉시 렌더링됩니다(`app/static/js/engine.js`). 서버 왕복이 없습니다.
- 서버 엔진(`app/renderer.py`)과 클라이언트 엔진은 같은 입력에 같은 결과를 냅니다(`tests/fixtures/render_cases.json` 119케이스로 검증).
- 문구는 코드가 아니라 DB에 있습니다. `/catalog` 화면에서 고치면 생성기에 바로 반영됩니다.

## 실행

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
flask init-db
flask seed                           # data/seed_catalog.json → DB
flask run                            # http://127.0.0.1:5000
pytest
```

`.env`의 `SECRET_KEY`는 임의의 긴 문자열로 바꾸세요(`python -c "import secrets;print(secrets.token_hex(32))"`). `.env`는 커밋하지 않습니다.

### Windows에서 `flask` 실행이 막히거나 SQLAlchemy DLL 오류가 날 때

회사 PC의 애플리케이션 제어 정책(스마트 앱 컨트롤 등)이 `.venv\Scripts\flask.exe`나 SQLAlchemy의 컴파일된 확장(`*.pyd`)을 막을 수 있습니다.

- `flask ...` 대신 `python -m flask ...` 를 쓰세요. 예: `python -m flask run`
- `ImportError: DLL load failed while importing _util_cy` 오류가 나면 SQLAlchemy를 순수 Python 모드로 쓰면 됩니다. 같은 이름의 `.py` 파일이 함께 들어 있으므로 `.pyd`만 지우면 됩니다.

```powershell
Get-ChildItem .venv\Lib\site-packages\sqlalchemy -Recurse -Filter *.pyd | Remove-Item
```

## 배포 (GitHub + Vercel + Supabase)

운영 환경은 Vercel(Python 서버리스) + Supabase Postgres입니다. SQLite 파일은 Vercel에서 유지되지 않으므로 운영 DB는 Supabase를 씁니다.

- `api/index.py` — Vercel 진입점, `vercel.json` — 모든 경로를 Flask로 전달
- `supabase/migrations/` — 스키마(RLS 켬)·seed SQL. 모델이나 seed를 바꾸면 `python scripts/export_supabase_sql.py`로 다시 생성
- `DATABASE_URL`에 Supabase 연결 문자열(`postgresql://...`)을 넣으면 자동으로 순수 Python 드라이버 `pg8000` + SSL로 접속합니다. 서버리스에서는 Supabase **Transaction pooler(6543 포트)** 주소를 쓰세요.

```bash
supabase link --project-ref <프로젝트 ref>
supabase db push                       # 스키마 + seed 적용
vercel env add SECRET_KEY production
vercel env add DATABASE_URL production
vercel --prod
```

## CLI

| 명령 | 동작 |
|---|---|
| `flask init-db` | 테이블 생성(있으면 유지) |
| `flask seed` | `seed_catalog.json` → DB. 이미 있는 code는 건너뜀(재실행 안전) |
| `flask reset-db` | 확인 후 전체 삭제 → 생성 → seed (`--yes`로 확인 생략) |
| `flask export-catalog [파일]` | 현재 DB 문구를 seed와 같은 JSON 구조로 내보내기 |

## 화면

| 경로 | 내용 |
|---|---|
| `/` | 생성기. `?history=<id>`, `?preset=<id>`로 해당 상태 열기 |
| `/history`, `/history/<id>` | 이력 검색·필터·즐겨찾기·삭제, 상세(복사·메일 앱·다시 작성) |
| `/contacts` | 주소록(기본 수신 대상 지정)·프로젝트 관리. 생성기 자동완성에 사용 |
| `/catalog` | 문구 관리: 블록 변주 추가·수정·순서·비활성화, 칩·입력 필드·공지 행 편집, 샘플 미리보기, 조사 규칙 경고 |
| `/settings` | 서명 6항목, 기본 모드·톤·대상·채널 |

## 테스트

```bash
pytest                         # 렌더러·카탈로그·API + JS 엔진 일치(Node가 있으면)
node tests/run_engine.mjs      # JS 엔진만 단독 비교
python tests/make_fixtures.py  # 렌더링 규칙을 바꿨을 때 픽스처 다시 생성 (Node 필요)
```

## 구조

```
app/
  __init__.py      create_app(), 확장·블루프린트·CLI 등록, SQLite PRAGMA
  models.py        SQLite 스키마
  catalog.py       seed JSON ↔ DB, 문구 관리 트리
  renderer.py      서버 렌더링 엔진 (engine.js와 동일 규칙)
  validation.py    입력 길이·날짜·시간·URL 검증, 조사 규칙 경고
  cli.py           init-db / seed / reset-db / export-catalog
  views/pages.py   화면
  views/api.py     JSON API (/api)
  templates/       base, generator, history, history_detail, contacts, catalog_admin, settings
  static/css/app.css
  static/js/       engine.js, generator.js, library.js, admin.js, common.js
data/seed_catalog.json
tests/             conftest, test_renderer, test_catalog, test_api, run_engine.mjs, fixtures/
```

## 보안 메모

- 템플릿은 직접 구현한 `{토큰}` 치환만 사용하고, 사용자가 고친 문구를 Jinja2로 렌더링하지 않습니다(SSTI 방지). 정의되지 않은 토큰은 원문 그대로 남습니다.
- 미리보기 HTML의 모든 값은 이스케이프됩니다. 복사·저장·mailto는 순수 텍스트만 씁니다.
- 모든 변경 요청은 CSRF 토큰(`X-CSRFToken` 헤더)이 필요합니다.

## 지시서와 다르게 정한 점

- `situations`에 `memo_sub` 컬럼을 추가했습니다(seed의 `memoSub` 보존용).
- `emailFields`, `fmtName`은 `settings` 테이블(`catalog_email_fields`, `catalog_fmt_name`)에 JSON으로 저장합니다.
- 날짜·시간 파싱은 두 엔진 모두 `YYYY-MM-DD` / `HH:MM` 형식만 인정하도록 엄격하게 맞췄습니다.
- 서명은 `/api/render`·`/api/history` 요청에 `sig`가 있으면 그것을, 없으면 설정값을 씁니다.
