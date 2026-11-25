# 작업 지시서 v2: 이메일·공지문 템플릿 생성기 — Flask 웹앱 전환

> **v2 변경 요약**: 고정 템플릿 10개 → **블록 조합형 문구 엔진**(인사말/본론 도입/핵심 내용/맺음말 + 변주 3~5개), 수신 대상 3종, 상황별 옵션 칩, 상황 맞춤 입력 필드, 실무 토글 3종, **이메일/공지문 모드 분리**(공지 4상황 × 게시판·슬랙·카카오톡), 실시간 하이라이트, 미리보기 직접 수정, mailto, 최근 기록·프리셋.
> 기준 구현은 아티팩트 **「이메일·공지문 템플릿 생성기 v2」**이며, 모든 문구 데이터는 함께 전달하는 **`seed_catalog.json`** 에 그대로 들어 있습니다.

## 0. 개요

| 항목 | 내용 |
|---|---|
| 목표 | v2 아티팩트를 Python Flask 웹앱으로 전환하고, 문구 데이터를 SQLite에서 관리 |
| 1차 범위 | 로컬 PC 구동(`flask run`), SQLite 단일 파일, 로그인 없는 1인 사용 |
| 기술 스택 | Python 3.11+, Flask 3.x, Flask-SQLAlchemy, Flask-WTF(CSRF), SQLite, Jinja2(페이지), Vanilla JS(실시간 미리보기) |
| 핵심 원칙 | ① 미리보기는 **브라우저에서 즉시** 렌더링(서버 왕복 없음) ② 서버 엔진(`renderer.py`)과 클라이언트 엔진(`engine.js`)은 **같은 입력 → 같은 결과** ③ 문구는 코드가 아니라 **DB**에 있음 |

---

## 1. 기능 명세

### 1-1. 작성 모드와 상황

| 모드 | 상황 (code) | 비고 |
|---|---|---|
| 이메일 | 일정 조율(`schedule`), 견적/자료 요청(`request`), 지연 사과(`delay`), 미팅 리마인드(`remind`), 업무 협조 요청(`coop`) | 수신 대상·톤 적용 |
| 공지문 | 사내 안내(`internal`), 교육·행사 모집(`recruit`), 시스템 점검(`maint`), 휴무·일정 변경(`holiday`) | 게시 채널·톤 적용 |

- 화면 상단 헤더에 `이메일 / 공지문` 탭. 모드별로 마지막 선택 상황을 각각 기억.

### 1-2. 문구 다양성 (블록 조합 + 셔플)

- 메일 본문은 고정 텍스트가 아니라 **블록 조합**으로 생성합니다.

| 블록 키 | 이메일 | 공지문 |
|---|---|---|
| `subj` 제목 | 상황×톤별 3개 | 상황별 3개 |
| `greet` 인사말 | **대상×톤별** 3~4개 (계절 인사 포함) | 톤별 3개 |
| `intro` 본론 도입 | 상황×톤별 3개 | 상황×톤별 3개 |
| `core` 핵심 내용 | 상황×톤별 3개 (일정 조율은 후보 1개용/복수용 별도) | 톤별 리드 문구 3개(예: `- 아 래 -`) |
| `close` 맺음말 | 상황별 마무리 3개 + 대상×톤별 맺음말 3~4개 | 상황별 마무리 + 톤별 맺음말 |

- 선택 인덱스는 `variant_seed = {subj, greet, intro, core, close}` 정수로 관리. 실제 선택은 `seed % 변주 개수`.
- `🎲 문구 새로고침`: 모든 seed를 1~2씩 무작위 증가. `문단별 바꾸기` 버튼(제목/인사말/본론 도입/핵심 내용/맺음말): 해당 seed만 +1.
- **조사 규칙**: 사용자 입력 토큰 바로 뒤에는 받침에 따라 달라지는 조사(은/는/이/가/을/를/과/와)를 쓰지 않습니다. `께`, `입니다`, `관련`, `건으로`, `까지`, `에`, `의` 등만 사용. 새 문구를 추가할 때도 이 규칙을 지키고, 템플릿 관리 화면 저장 시 정규식으로 경고합니다(`\}\s*(은|는|이|가|을|를|과|와)\b`).
- **계절 인사**: `%s%` 자리표시자를 현재 월 기준 문장으로 치환(`seasonal_greetings` 테이블, 12개월).

### 1-3. 수신 대상(관계) — 이메일 전용

| code | 이름 | 수신자명 비었을 때 기본 호칭 | 반영 |
|---|---|---|---|
| `ext` | 외부 거래처 | 담당자님 | `{to}께,` 격식 인사, 계절 인사, "귀사의 무궁한 발전" 등 |
| `dept` | 타 부서 협업 | 담당자님 | 협업 감사 인사, "함께 잘 마무리" 등 |
| `team` | 사내 팀원 | 팀원 여러분 | 짧은 인사, 보내는 사람은 **이름만**, "고맙습니다" 등 |

- 보내는 사람 `{sender}` = `team`이면 이름만, 그 외에는 `소속 부서 + 이름`.

### 1-4. 상황별 옵션 칩

- 상황마다 칩 4개. 칩을 켜고 끄면 해당 문장이 즉시 추가·제거됩니다. 상황별 기본 ON 칩은 `default_on`.
- 칩 문장에 줄바꿈이 있으면 독립 문단, 없으면 한 문단으로 묶어 출력.
- 예) 지연 사과: `원인 간략 설명 포함`(지연 사유 입력값을 문단으로), `변경된 일정 강조`(▶ 변경 완료 예정일), `재발 방지 약속`, `진행 상황 공유`.
- 공지문 칩은 `※ ...` 안내문으로 출력(예: 시스템 점검 `서비스 중단 강조`, `사전 저장 권고`, `조기 종료 가능`, `연장 가능성 안내`).
- 칩 선택 상태는 `모드.상황` 키별로 따로 저장.

### 1-5. 상황 맞춤 입력 필드

| 모드 / 상황 | 입력 필드 |
|---|---|
| 이메일 공통 | 수신자명, 수신자 이메일(선택, mailto용), 프로젝트명 |
| 일정 조율 | **후보 일정 1~3개**(날짜+시간, `+ 후보 일정 추가` / `×` 삭제), 추가 전달 사항(선택) |
| 견적/자료 요청 | 요청 항목(여러 줄) |
| 지연 사과 | **기존 마감일 vs 변경 예정일**, 지연 사유 |
| 미팅 리마인드 | 미팅 날짜·시간, **장소**, **화상회의 링크**(Zoom·Teams 등), 안건/참고 사항 |
| 업무 협조 요청 | 협조 요청 내용(여러 줄) |
| 사내 안내 | 안내 제목, 날짜·시간(선택), 대상, 주요 내용(한 줄 = 한 항목), 문의처 |
| 교육·행사 모집 | 교육·행사명, 날짜·시간, 장소, 대상, 내용, 신청 방법, 신청 마감, 문의처 |
| 시스템 점검 | 점검 시스템, 시작일·시간, 종료일·시간, 영향 범위, 점검 내용, 문의처 |
| 휴무·일정 변경 | 휴무·변경 사유, 시작일·종료일, 대상, 변경 사항, 문의처 |

- 필드 정의는 `situations.fields_json`에 저장(키, 라벨, 보조 설명, 타입, placeholder, 반폭 여부, 연결 토큰).
- 입력값 저장 키: 이메일 공통은 `to`, `proj` 등 그대로, 상황별 메모는 `memo.<상황>`, 공지 필드는 `<상황>.<필드>`(예: `maint.d1`). 상황을 바꿔도 각 상황의 입력값이 유지됩니다.
- 날짜 표기: `12월 3일(목)`, 시간: `오후 2시`, `오전 9시 30분`. 기간은 `12월 6일(일) 오후 10시 ~ 12월 7일(월) 오전 6시`, 휴무는 `~ (N일간)`.
- 휴무 공지의 `{resume}`(업무 재개일) = 종료일 다음 날, 토·일이면 다음 월요일로 계산.

### 1-6. 실무 토글 3종

| 토글 | ON일 때 | 비고 |
|---|---|---|
| 첨부파일 있음 | 파일명 입력칸 노출, 이메일: "관련 자료를 첨부드리오니 확인 부탁드립니다." + `· 첨부: 파일명` / 공지: `※ 첨부 파일: 파일명` | **모드별로 ON/OFF와 파일명 따로 저장** |
| 회신 기한 강조 | 날짜 선택기 노출, "바쁘시겠지만 12월 1일(화)까지 회신 부탁드립니다." | 이메일 전용 |
| 내 서명 자동 삽입 | 본문 하단에 구분선 + 서명(이름 직함 / 부서 / 회사 / T. 연락처 · E. 이메일) | 이메일 + 공지(게시판 형식) |

- 서명 정보(이름·직함·부서·회사·연락처·이메일)는 **settings 테이블**에 저장하고, 브라우저 `localStorage`에도 캐시(오프라인·초기 로딩용). 값이 없는 줄은 생략.

### 1-7. 공지문 전용 포맷

- 본문은 개조식 행으로 자동 정렬: 상황별 `notice_rows`(라벨, 토큰, 목록 여부, 선택 여부). 선택 행은 값이 비면 생략.

| 채널 | 제목 처리 | 행 형식 | 안내문(칩) | 마무리 |
|---|---|---|---|---|
| 사내 게시판 `board` | 별도 제목 | `■ 일시: …` / 목록은 `■ 주요 내용` + `  - 항목` | `※ …` | `{발신 부서} 드림` + 서명 |
| 슬랙 `slack` | 본문 첫 줄 `*[공지] …*` | `• *일시*: …` / 목록 `    ◦ 항목` | `> ※ …` (인용) | 서명 없음 |
| 카카오톡 `kakao` | 본문 첫 줄 `📢 [공지] …` | `▶ 일시: …` / 목록 `   · 항목` | `※ …` | `- {발신 부서} -` |

- 주요 내용 입력의 각 줄 앞 기호(`-`, `•`, `·`, `◦`, `*`, `▶`, `■`)는 제거 후 채널 형식으로 다시 붙임.
- 발신 부서 `{issuer}` = 서명의 부서, 없으면 이름.

### 1-8. UX 디테일

| 기능 | 명세 |
|---|---|
| 실시간 하이라이트 | 미리보기에서 입력값은 연한 파란색 `<mark>`, **방금 입력한 필드의 값은 1.5초간 연노랑**으로 강조 후 파란색으로 전환. 빈 값은 회색 `[라벨]`. 복사·저장·mailto는 **순수 텍스트만** |
| 직접 수정 모드 | `직접 수정` → 제목 input + 본문 textarea로 전환(현재 생성 결과로 채움). 수정 중에는 왼쪽 입력을 바꿔도 수정본 유지, 셔플 버튼 비활성, 상단 배너에 `초기화`(자동 생성으로 복귀) |
| 복사 | `제목 복사`, `본문 복사`(성공 시 1.5초 "복사됨 ✓"). 클립보드 API 실패 시 textarea + `execCommand('copy')` |
| 메일 앱에서 열기 | `mailto:수신자?subject=…&body=…`(줄바꿈 `\r\n`, URL 인코딩). 수정본이 있으면 수정본 사용. 본문 2,000자 초과 시 "일부 메일 앱은 긴 본문을 자를 수 있어요" 안내 |
| 최근 기록 | 본문 복사·메일 열기 시 자동 저장. 사이드 패널에 최근 5건, 클릭 시 당시 설정(+수정본) 복원. Flask에서는 `history` 테이블에 전부 저장하고 패널은 최근 5건만 표시 |
| 프리셋 | 현재 모드·상황·대상·톤·채널·칩·토글·입력값을 이름 붙여 저장(최대 20개), 불러오기·삭제(삭제 되돌리기 토스트) |
| 입력값 모두 지우기 | 모든 입력 초기화 + 토스트 `되돌리기` (5초) |
| 반응형 | 860px 이하 세로 배치(입력 → 미리보기), 440px 이하 버튼 꽉 채우기 |
| 다크 모드 | `prefers-color-scheme` 대응 (`light-dark()` 변수) |

### 1-9. 보안·안정성 (필수)

- **템플릿 치환은 직접 구현한 토큰 치환만**: 정규식 `\{(\w+)\}`. 사용자 수정 템플릿을 **절대 Jinja2로 렌더링하지 않음**(SSTI). 정의되지 않은 토큰은 원문 유지.
- 미리보기 HTML 출력 시 모든 값 이스케이프(JS `esc()` / Jinja 자동 이스케이프). 테스트: `<img src=x onerror=alert(1)>` 입력 시 태그가 생성되지 않아야 함.
- CSRF: `Flask-WTF CSRFProtect`, fetch 요청은 `X-CSRFToken` 헤더.
- `SECRET_KEY`는 `.env`, 저장소 커밋 금지.
- 입력 길이 제한: 수신자명 50자, 프로젝트명·공지 제목 100자, 여러 줄 입력 2,000자, 파일명 200자, 날짜 `YYYY-MM-DD`, 시간 `HH:MM`, URL은 `http(s)://`만 허용.
- DB 저장 실패 시에도 미리보기·복사는 계속 동작하고 토스트로만 안내.

---

## 2. 로컬 구동 구성

### 2-1. 디렉터리 구조

```
mailgen/
├── app/
│   ├── __init__.py          # create_app(), 확장 초기화, 블루프린트·CLI 등록
│   ├── config.py
│   ├── extensions.py        # db, csrf
│   ├── models.py            # 3장 스키마
│   ├── catalog.py           # DB → 카탈로그 JSON 조립 (seed_catalog.json과 동일 구조)
│   ├── renderer.py          # 서버 렌더링 엔진 (engine.js와 동일 규칙)
│   ├── cli.py               # init-db / seed / reset-db / export-catalog
│   ├── views/
│   │   ├── pages.py         # 화면 라우트
│   │   └── api.py           # JSON API (/api)
│   ├── templates/
│   │   ├── base.html        # 헤더(모드 탭), 내비게이션, 토스트
│   │   ├── generator.html   # 메인 생성기 (아티팩트 v2 UI)
│   │   ├── history.html / history_detail.html
│   │   ├── contacts.html
│   │   ├── catalog_admin.html   # 문구 관리 (블록·칩·필드)
│   │   └── settings.html
│   └── static/
│       ├── css/app.css      # 아티팩트 v2 CSS 이식
│       └── js/
│           ├── engine.js    # 토큰 치환·블록 조합 (아티팩트 v2 로직 추출, 순수 함수)
│           ├── generator.js # 폼·미리보기·칩·토글·직접 수정·복사·mailto
│           ├── library.js   # 최근 기록·프리셋 패널
│           └── admin.js     # 문구 관리 미리보기
├── data/
│   └── seed_catalog.json    # 함께 전달한 파일 그대로
├── instance/mailgen.sqlite3 # 자동 생성 (git 제외)
├── tests/
│   ├── fixtures/render_cases.json   # 서버·클라이언트 공용 테스트 케이스
│   ├── test_renderer.py
│   ├── test_catalog.py
│   └── test_api.py
├── .env.example  .gitignore  requirements.txt  run.py  README.md
```

### 2-2. requirements.txt

```
Flask>=3.0,<4
Flask-SQLAlchemy>=3.1,<4
Flask-WTF>=1.2,<2
python-dotenv>=1.0,<2
pytest>=8,<9
```

### 2-3. 환경 변수 (`.env.example`)

```
FLASK_APP=run.py
FLASK_DEBUG=1
SECRET_KEY=change-me-to-a-random-string
DATABASE_URL=sqlite:///mailgen.sqlite3
```

- `DATABASE_URL`이 없으면 `instance/mailgen.sqlite3` 사용, `create_app()`에서 instance 폴더 생성.
- SQLite 연결 시 `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`.

### 2-4. 실행 순서 (README에 그대로 기재)

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

### 2-5. CLI

| 명령 | 동작 |
|---|---|
| `flask init-db` | 테이블 생성(있으면 유지) |
| `flask seed` | `seed_catalog.json`의 모드·상황·대상·블록 변주·칩·공지 행·계절 인사·옵션 문구 + 기본 설정 입력. **이미 있는 code는 건너뜀**(재실행 안전) |
| `flask reset-db` | 확인 후 전체 삭제 → 생성 → seed |
| `flask export-catalog [파일]` | 현재 DB 문구를 seed와 같은 JSON 구조로 내보내기(백업·이관용) |

---

## 3. SQLite 데이터베이스 설계

### 3-1. 관계 요약

```
situations 1──< template_variants (block 단위 변주, 대상·톤 조건)
situations 1──< chips
situations 1──< notice_rows (공지 전용)
audiences  1──< template_variants (greet/close 공통 블록)
seasonal_greetings, option_texts   (공통 문구)
history, presets, contacts, projects, settings
variant_revisions >──1 template_variants (수정 이력)
```

### 3-2. DDL

```sql
-- 상황 (이메일 5 + 공지 4)
CREATE TABLE situations (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  mode          TEXT NOT NULL CHECK (mode IN ('email','notice')),
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  is_active     INTEGER NOT NULL DEFAULT 1,
  -- 이메일 메모 필드 설정
  memo_mode     TEXT CHECK (memo_mode IN ('opt','core','chip')),   -- opt: 값 있을 때 문단 추가 / core: 핵심 문구에 포함 / chip: 칩으로 포함
  memo_name     TEXT,          -- 빈 값 placeholder 라벨 (예: 지연 사유)
  memo_label    TEXT,          -- 입력칸 라벨
  memo_placeholder TEXT,
  -- 공지 일시 표기 방식
  when_type     TEXT CHECK (when_type IN ('dt','range','days')),
  when_label    TEXT,
  fields_json   TEXT NOT NULL DEFAULT '[]',  -- 상황 맞춤 입력 필드 정의 (1-5 참조)
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (mode, code)
);

-- 수신 대상
CREATE TABLE audiences (
  code        TEXT PRIMARY KEY CHECK (code IN ('ext','dept','team')),
  name        TEXT NOT NULL,
  default_to  TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0
);

-- 문구 변주 (블록 단위, 한 행 = 문장 변주 1개)
CREATE TABLE template_variants (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  situation_id  INTEGER REFERENCES situations(id) ON DELETE CASCADE,  -- NULL = 공통 블록
  mode          TEXT NOT NULL CHECK (mode IN ('email','notice')),
  block         TEXT NOT NULL CHECK (block IN
                 ('subj','greet','intro','core','core_multi','close_lead','close','lead')),
  audience      TEXT REFERENCES audiences(code),   -- greet/close(이메일 공통)만 사용
  tone          TEXT CHECK (tone IN ('formal','brief')),  -- 공지 subj는 NULL
  text          TEXT NOT NULL,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  is_active     INTEGER NOT NULL DEFAULT 1,
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_variant_lookup ON template_variants(mode, situation_id, block, audience, tone, is_active, sort_order);

-- 변주 수정 이력
CREATE TABLE variant_revisions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id  INTEGER NOT NULL REFERENCES template_variants(id) ON DELETE CASCADE,
  old_text    TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 옵션 칩
CREATE TABLE chips (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  situation_id  INTEGER NOT NULL REFERENCES situations(id) ON DELETE CASCADE,
  code          TEXT NOT NULL,
  label         TEXT NOT NULL,
  text_formal   TEXT,          -- 이메일
  text_brief    TEXT,          -- 이메일
  text          TEXT,          -- 공지 (톤 공통)
  default_on    INTEGER NOT NULL DEFAULT 0,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  UNIQUE (situation_id, code)
);

-- 공지 개조식 행
CREATE TABLE notice_rows (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  situation_id  INTEGER NOT NULL REFERENCES situations(id) ON DELETE CASCADE,
  label         TEXT NOT NULL,       -- 일시, 대상, 주요 내용 ...
  token         TEXT NOT NULL,       -- nWhen, target, content ...
  is_list       INTEGER NOT NULL DEFAULT 0,
  is_optional   INTEGER NOT NULL DEFAULT 0,
  sort_order    INTEGER NOT NULL DEFAULT 0
);

-- 계절 인사 (%s%)
CREATE TABLE seasonal_greetings (
  month  INTEGER PRIMARY KEY CHECK (month BETWEEN 1 AND 12),
  text   TEXT NOT NULL
);

-- 토글 문구 (attach, files, due, nAttach, nFiles)
CREATE TABLE option_texts (
  key          TEXT PRIMARY KEY,
  text_formal  TEXT,
  text_brief   TEXT,
  text         TEXT
);

-- 작성 이력
CREATE TABLE history (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  mode            TEXT NOT NULL,
  situation_code  TEXT NOT NULL,
  audience        TEXT,
  tone            TEXT NOT NULL,
  channel         TEXT,                     -- board/slack/kakao (공지)
  inputs_json     TEXT NOT NULL,            -- 당시 입력값 전체
  chips_json      TEXT NOT NULL,
  toggles_json    TEXT NOT NULL,
  variant_seed_json TEXT NOT NULL,          -- {subj,greet,intro,core,close}
  catalog_rev     INTEGER,                  -- 생성 당시 문구 리비전
  to_name         TEXT,                     -- 검색용 비정규화
  project_name    TEXT,
  subject         TEXT NOT NULL,
  body            TEXT NOT NULL,
  is_edited       INTEGER NOT NULL DEFAULT 0,  -- 직접 수정본 여부
  action          TEXT NOT NULL CHECK (action IN ('copy','mailto','draft')),
  is_favorite     INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_history_created ON history(created_at DESC);
CREATE INDEX idx_history_search  ON history(to_name, project_name);

-- 프리셋
CREATE TABLE presets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,   -- mode, sit, aud, tone, fmt, chips, tg, f
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 주소록 / 프로젝트 (자동완성)
CREATE TABLE contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL, company TEXT, email TEXT,
  default_audience TEXT REFERENCES audiences(code),   -- 선택 시 수신 대상 자동 지정
  use_count INTEGER NOT NULL DEFAULT 0, last_used_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE, is_archived INTEGER NOT NULL DEFAULT 0,
  use_count INTEGER NOT NULL DEFAULT 0, last_used_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 설정 (key-value)
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
-- sig_name, sig_title, sig_dept, sig_company, sig_phone, sig_email,
-- default_mode, default_tone, default_audience, default_channel, catalog_rev
```

### 3-3. 데이터 규칙

- 문구(변주·칩·행·필드)를 수정하면 `settings.catalog_rev += 1`. 클라이언트는 `/api/catalog` 응답의 `rev`로 캐시 무효화.
- 변주 수정 시 기존 텍스트를 `variant_revisions`에 남기고 UPDATE(한 트랜잭션). 삭제 대신 `is_active=0`.
- **블록별 최소 1개 활성 변주** 보장: 마지막 하나는 비활성화 불가(409).
- 이력 저장 시 수신자명·프로젝트명이 주소록/프로젝트와 정확히 일치하면 `use_count`, `last_used_at` 갱신. 자동 생성은 하지 않음.
- 같은 제목+본문으로 3초 안에 다시 저장 요청 시 1건만 저장.

---

## 4. 화면·API 명세

### 4-1. 화면

| 경로 | 화면 | 내용 |
|---|---|---|
| `GET /` | 생성기 | 아티팩트 v2와 동일 UI. 왼쪽 하단 패널 = 최근 기록 5건(API) / 프리셋 |
| `GET /?history=<id>` / `?preset=<id>` | 생성기 | 해당 이력·프리셋 상태로 열기 |
| `GET /history` | 이력 | 검색(수신자·프로젝트·제목·본문), 모드·상황 필터, 즐겨찾기, 20건 페이지 |
| `GET /history/<id>` | 이력 상세 | 제목/본문 복사, 메일 앱 열기, 다시 작성, 즐겨찾기, 삭제 |
| `GET /contacts` | 주소록·프로젝트 | CRUD, 수신자별 기본 수신 대상 지정 |
| `GET /catalog` | 문구 관리 | 모드 → 상황 → 블록 트리. 변주 추가·수정·순서 변경·비활성화, 칩·입력 필드·공지 행 편집, 샘플 값 실시간 미리보기, 조사 규칙 경고 |
| `GET /settings` | 설정 | 서명 6항목, 기본 모드·톤·대상·채널 |

### 4-2. JSON API (`/api`)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/catalog` | 전체 문구 카탈로그 + `rev`. **구조는 `seed_catalog.json`과 동일**(클라이언트 엔진이 그대로 사용) |
| POST | `/api/render` | `{state}` → `{subject, body}` (서버 엔진) |
| POST | `/api/history` | `{state, action, edited?:{subject,body}}` → 서버에서 다시 렌더링해 저장. `edited`가 있으면 수정본 저장 + `is_edited=1` |
| GET | `/api/history?limit=5` | 최근 기록 |
| GET/PATCH/DELETE | `/api/history[/<id>]` | 검색·즐겨찾기·삭제 |
| GET/POST/PUT/DELETE | `/api/presets[/<id>]` | 프리셋 CRUD |
| GET | `/api/contacts?q=` · `/api/projects?q=` | 자동완성(사용 빈도순 8건) |
| POST/PUT/DELETE | `/api/contacts[/<id>]` · `/api/projects[/<id>]` | CRUD |
| GET/PUT | `/api/settings` | 서명·기본값 |
| PUT/POST/PATCH | `/api/catalog/variants[/<id>]`, `/api/catalog/chips[/<id>]`, `/api/catalog/rows[/<id>]`, `/api/catalog/situations/<id>/fields` | 문구 관리 |

- `state` 구조(아티팩트 v2와 동일):

```json
{
  "mode": "email",
  "sit": {"email": "delay", "notice": "internal"},
  "aud": "ext", "tone": "formal", "fmt": "board",
  "f": {"to": "김민수 팀장님", "proj": "2027 브랜드 리뉴얼", "oldDate": "2026-12-04", "newDate": "2026-12-11",
        "memo.delay": "원자재 수급 지연", "cands": [{"d": "2026-12-03", "t": "14:00"}],
        "files.email": "1차_시안.pdf", "maint.d1": "2026-12-06"},
  "chips": {"email.delay": ["cause", "emph"]},
  "tg": {"attach.email": true, "attach.notice": false, "due": false, "sig": true},
  "v": {"subj": 0, "greet": 2, "intro": 1, "core": 0, "close": 3}
}
```

- 오류 형식: `{"error": {"code": "VALIDATION_ERROR", "message": "…", "field": "proj"}}`.

### 4-3. 렌더링 규칙 (`renderer.py` ↔ `engine.js`)

**토큰**

| 토큰 | 값 | 빈 값 처리 |
|---|---|---|
| `{to}` | 수신자명 | 대상별 기본 호칭(하이라이트 없음) |
| `{sender}` | team: 이름 / 그 외: 부서+이름 | `[보내는 사람]` |
| `{proj}` `{memo}` | 입력값 | `[프로젝트명]`, `[상황별 memo_name]` |
| `{cands}` | 1개: `12월 3일(목) 오후 2시` / 2개 이상: `1) …` 줄바꿈 목록 | `[후보 일정]` |
| `{oldDate}` `{newDate}` `{due}` | 날짜 포맷 | `[기존 마감일]` 등 |
| `{when}` | 미팅 날짜+시간 | `[미팅 일시]` |
| `{place}` `{link}` `{files}` | 입력값 | `[장소]` 등 |
| `{issuer}` | 서명 부서 → 없으면 이름 | `[발신 부서]` |
| `{sig1}~{sig3}` | 서명 줄 | 모두 비면 `{sig0}` = `[서명 정보 입력]` |
| `{nTitle}` `{target}` `{apply}` `{contact}` | 공지 입력 | `[필드 라벨]` |
| `{nWhen}` | `when_type`별 일시/기간 | `[when_label]` |
| `{applyDue}` `{resume}` | 날짜 | `[신청 마감]`, `[업무 재개일]` |
| `{content}` | 채널별 접두 기호 목록 | 접두 + `[필드 라벨]` |
| `%s%` | 이번 달 계절 인사 | – |

**이메일 조립 순서** (빈 문단 제외, 문단 사이 빈 줄 1개)

1. `greet[대상][톤]` 2. `intro[상황][톤]` 3. `core`(일정 조율은 후보 2개 이상이면 `core_multi`) — 미팅 리마인드는 `· 일시 / · 장소(링크 없거나 장소 있을 때) / · 화상회의(링크 있을 때)` 줄 추가 4. 메모(`memo_mode=opt`이고 값 있을 때) 5. 칩: 줄바꿈 있는 칩은 각각 문단 → 한 줄 칩은 묶어서 한 문단 6. 첨부 토글 7. 회신 기한 토글 8. `close_lead[상황][톤]` + `close[대상][톤]` 9. 서명 토글

**공지 조립 순서**

- 게시판: `greet+intro` → `lead` + 빈 줄 + 행 목록 → 안내문(칩 + 첨부) → `close_lead + close` → `{issuer} 드림` → 서명
- 슬랙: `*제목*` → `greet intro` → 행 목록 → `> ` 안내문 → 마무리
- 카카오톡: `📢 제목` → `greet` 줄바꿈 `intro` → `lead` + 행 목록 → 안내문 → 마무리 → `- {issuer} -`

**출력**

- HTML: 값 `<mark data-g="그룹">`, 빈 값 `<span class="ph">`, 기본 호칭 등은 일반 텍스트. 텍스트: 태그 없는 순수 문자열.
- 공용 픽스처 `tests/fixtures/render_cases.json`(최소 30케이스: 9상황 × 톤 × 대상/채널 조합 + 빈 값 + 셔플 seed + 칩 조합)으로 Python·JS 결과 일치 검증(JS는 Node로 실행하는 스크립트 `tests/run_engine.mjs`).

---

## 5. 프론트엔드 요구사항

- 아티팩트 v2의 CSS를 `static/css/app.css`로, 렌더링 로직(`R`, `fill`, `buildEmail`, `buildNotice`, 날짜 함수)을 DOM 없이 동작하는 `engine.js`로 분리.
- 생성기 첫 로드 시 `/api/catalog`를 한 번 받아 메모리에 두고(`rev` 같으면 localStorage 캐시 사용) 이후 입력·셔플·칩 변경은 **네트워크 없이** 렌더링.
- 입력 폼은 상황 변경 시에만 다시 그림(입력 중 포커스 유지). 세그먼트·칩·토글은 `aria-pressed`/`checked`만 갱신.
- 수신자명 자동완성 선택 시 수신자 이메일·기본 수신 대상도 채움.
- 본문 복사 / 메일 앱 열기 → `/api/history` 저장 → 최근 기록 패널 갱신. 서버 저장 실패 시 localStorage 최근 기록으로 대체 저장.
- 접근성: 모든 버튼 44px 내외 터치 영역, `:focus-visible` 표시, 토글은 `<input type=checkbox>` 기반, 미리보기 `aria-live="polite"`.

---

## 6. 테스트 및 완료 기준

### 6-1. 자동 테스트

- `test_renderer.py`: 9개 상황 × 2톤 × (이메일 3대상 / 공지 3채널) 렌더링, 빈 값 placeholder, 후보 일정 0/1/3개, 기간 계산(N일간), 재개일 주말 건너뛰기, 계절 인사 월별, 칩 ON/OFF, 첨부 모드 분리, `{{7*7}}`·`<script>` 입력 그대로 출력.
- `test_catalog.py`: seed → `/api/catalog` 결과가 `seed_catalog.json`과 동일, 마지막 활성 변주 비활성화 409, 수정 시 `catalog_rev` 증가·이력 생성, 조사 규칙 경고.
- `test_api.py`: render/history/presets/contacts/settings CRUD, 검증 오류 400, 중복 저장 방지, `edited` 저장.
- 엔진 일치: `render_cases.json` 전 케이스에서 Python == JS.

### 6-2. 수동 확인 체크리스트

- [ ] 2-4 명령만으로 새 PC에서 실행된다. `flask seed` 2회 실행해도 중복 없음.
- [ ] 이메일/공지문 탭 전환 시 상황·입력 필드·칩·옵션이 모드에 맞게 바뀌고, 각 모드의 입력값이 유지된다.
- [ ] `🎲 문구 새로고침`과 문단별 바꾸기로 같은 조건에서 다른 문장이 나온다.
- [ ] 수신 대상 전환 시 호칭·인사·맺음말·보내는 사람 표기가 바뀐다.
- [ ] 칩 토글 시 문장이 즉시 추가·제거된다.
- [ ] 일정 조율 후보 일정 추가(최대 3)·삭제, 1개일 때 문장형/2개 이상 목록형으로 바뀐다.
- [ ] 지연 사과의 기존/변경 날짜, 미팅 리마인드의 장소·링크가 본문에 반영된다.
- [ ] 첨부·회신 기한·서명 토글이 동작하고, 서명은 새로고침 후에도 유지된다.
- [ ] 공지 3채널 형식이 1-7 표와 일치한다.
- [ ] 입력 중인 값이 노란색 → 파란색으로 하이라이트되고, 복사 결과에는 서식이 없다.
- [ ] 직접 수정 → 왼쪽 입력 변경해도 유지 → 초기화로 복귀. 복사·mailto에 수정본 반영.
- [ ] 메일 앱 열기 시 제목·본문·수신자가 채워진다.
- [ ] 최근 기록 5건, 프리셋 저장·불러오기·삭제 되돌리기가 동작한다.
- [ ] 문구 관리에서 변주를 추가하면 생성기 셔플 후보에 바로 포함된다.
- [ ] `<img src=x onerror=alert(1)>` 입력 시 실행되지 않는다. 375px 폭에서 가로 스크롤 없음.

---

## 7. 작업 순서 (권장)

1. 골격·설정·`.env`·requirements
2. 모델 + `init-db`/`seed`/`reset-db`/`export-catalog`, `catalog.py`(DB → JSON) + `test_catalog.py`
3. `engine.js` 추출(아티팩트 v2 기준) → `renderer.py` 포팅 → 공용 픽스처 테스트 통과
4. 생성기 화면(이메일 모드) + `/api/catalog`, `/api/render`
5. 공지문 모드·3채널
6. 직접 수정·복사·mailto·이력 저장·최근 기록 패널
7. 프리셋·주소록·프로젝트·자동완성
8. 설정(서명)
9. 문구 관리 화면(변주·칩·필드·행, 리비전)
10. 전체 테스트·체크리스트·README

---

## 부록 A. `seed_catalog.json` 구조

함께 전달하는 `seed_catalog.json`은 아티팩트 v2에 들어 있는 문구 데이터를 그대로 추출한 파일입니다. `flask seed`는 이 파일만 읽어 DB를 채우고, `/api/catalog`는 DB에서 같은 구조로 다시 조립합니다.

```
{
  "season":      {"1": "...", ..., "12": "..."},                 → seasonal_greetings
  "aud":         {"ext": {"name","defTo"}, "dept": ..., "team": ...}   → audiences
  "greet":       {"<aud>": {"formal": [..], "brief": [..]}}       → template_variants(mode=email, situation=NULL, block=greet)
  "close":       {"<aud>": {"formal": [..], "brief": [..]}}       → template_variants(block=close)
  "opt":         {"attach": {formal,brief}, "files", "due": {..}, "nAttach": {..}, "nFiles"} → option_texts
  "emailFields": {"to": {l,ph,half,type,sub,tok}, ...}            → 이메일 공통/상황 필드 정의 사전
  "email": {
    "order": [...],
    "sits": {"<code>": {
      "name", "fields": [필드 키], "memoMode", "memoName", "memoLabel", "memoSub?", "memoPh",
      "subj"|"intro"|"core"|"coreMulti?"|"closeLead": {"formal": [..], "brief": [..]},
      "chips": [{"id","label","on?","formal","brief"}]
    }}
  },
  "notice": {
    "order": [...], "fmtName": {...},
    "greet"|"lead"|"close": {"formal": [..], "brief": [..]},      → template_variants(mode=notice, situation=NULL)
    "sits": {"<code>": {
      "name", "when", "whenLabel",
      "fields": [{"k","l","sub?","type?","ph?","half?","tok?"}],  → situations.fields_json
      "rows":   [{"l","tok","list?","opt?"}],                       → notice_rows
      "subj":   [..],                                              → template_variants(block=subj, tone=NULL)
      "intro":  {"formal": [..], "brief": [..]},
      "chips":  [{"id","label","on?","text"}],
      "closeLead": {"formal": [..], "brief": [..]}
    }}
  }
}
```

**수량 요약**: 이메일 5상황 × (제목·도입·핵심·마무리 각 톤별 3개) + 일정 조율 복수 후보용 핵심 6개, 이메일 칩 20개, 대상별 인사말 19개·맺음말 19개, 공지 4상황 × (제목 3·도입 톤별 3) + 공통 인사·리드·맺음 각 6개, 공지 칩 16개, 계절 인사 12개.
