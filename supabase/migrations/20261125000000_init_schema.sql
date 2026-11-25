-- 테이블·인덱스 (app/models.py 에서 생성)

CREATE TABLE audiences (
	code TEXT NOT NULL, 
	name TEXT NOT NULL, 
	default_to TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (code), 
	CHECK (code IN ('ext','dept','team'))
);

CREATE TABLE history (
	id SERIAL NOT NULL, 
	mode TEXT NOT NULL, 
	situation_code TEXT NOT NULL, 
	audience TEXT, 
	tone TEXT NOT NULL, 
	channel TEXT, 
	inputs_json TEXT NOT NULL, 
	chips_json TEXT NOT NULL, 
	toggles_json TEXT NOT NULL, 
	variant_seed_json TEXT NOT NULL, 
	catalog_rev INTEGER, 
	to_name TEXT, 
	project_name TEXT, 
	subject TEXT NOT NULL, 
	body TEXT NOT NULL, 
	is_edited INTEGER NOT NULL, 
	action TEXT NOT NULL, 
	is_favorite INTEGER NOT NULL, 
	created_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (action IN ('copy','mailto','draft'))
);

CREATE INDEX idx_history_created ON history (created_at DESC);

CREATE INDEX idx_history_search ON history (to_name, project_name);

CREATE TABLE option_texts (
	key TEXT NOT NULL, 
	text_formal TEXT, 
	text_brief TEXT, 
	text TEXT, 
	PRIMARY KEY (key)
);

CREATE TABLE presets (
	id SERIAL NOT NULL, 
	name TEXT NOT NULL, 
	snapshot_json TEXT NOT NULL, 
	created_at TEXT NOT NULL, 
	updated_at TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE projects (
	id SERIAL NOT NULL, 
	name TEXT NOT NULL, 
	is_archived INTEGER NOT NULL, 
	use_count INTEGER NOT NULL, 
	last_used_at TEXT, 
	created_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE seasonal_greetings (
	month INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	PRIMARY KEY (month), 
	CHECK (month BETWEEN 1 AND 12)
);

CREATE TABLE settings (
	key TEXT NOT NULL, 
	value TEXT, 
	PRIMARY KEY (key)
);

CREATE TABLE situations (
	id SERIAL NOT NULL, 
	mode TEXT NOT NULL, 
	code TEXT NOT NULL, 
	name TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	is_active INTEGER NOT NULL, 
	memo_mode TEXT, 
	memo_name TEXT, 
	memo_label TEXT, 
	memo_sub TEXT, 
	memo_placeholder TEXT, 
	when_type TEXT, 
	when_label TEXT, 
	fields_json TEXT NOT NULL, 
	updated_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (mode, code), 
	CHECK (mode IN ('email','notice')), 
	CHECK (memo_mode IN ('opt','core','chip')), 
	CHECK (when_type IN ('dt','range','days'))
);

CREATE TABLE chips (
	id SERIAL NOT NULL, 
	situation_id INTEGER NOT NULL, 
	code TEXT NOT NULL, 
	label TEXT NOT NULL, 
	text_formal TEXT, 
	text_brief TEXT, 
	text TEXT, 
	default_on INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (situation_id, code), 
	FOREIGN KEY(situation_id) REFERENCES situations (id) ON DELETE CASCADE
);

CREATE TABLE contacts (
	id SERIAL NOT NULL, 
	display_name TEXT NOT NULL, 
	company TEXT, 
	email TEXT, 
	default_audience TEXT, 
	use_count INTEGER NOT NULL, 
	last_used_at TEXT, 
	created_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(default_audience) REFERENCES audiences (code)
);

CREATE TABLE notice_rows (
	id SERIAL NOT NULL, 
	situation_id INTEGER NOT NULL, 
	label TEXT NOT NULL, 
	token TEXT NOT NULL, 
	is_list INTEGER NOT NULL, 
	is_optional INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(situation_id) REFERENCES situations (id) ON DELETE CASCADE
);

CREATE TABLE template_variants (
	id SERIAL NOT NULL, 
	situation_id INTEGER, 
	mode TEXT NOT NULL, 
	block TEXT NOT NULL, 
	audience TEXT, 
	tone TEXT, 
	text TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	is_active INTEGER NOT NULL, 
	updated_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (mode IN ('email','notice')), 
	CHECK (block IN ('subj','greet','intro','core','core_multi','close_lead','close','lead')), 
	CHECK (tone IN ('formal','brief')), 
	FOREIGN KEY(situation_id) REFERENCES situations (id) ON DELETE CASCADE, 
	FOREIGN KEY(audience) REFERENCES audiences (code)
);

CREATE INDEX idx_variant_lookup ON template_variants (mode, situation_id, block, audience, tone, is_active, sort_order);

CREATE TABLE variant_revisions (
	id SERIAL NOT NULL, 
	variant_id INTEGER NOT NULL, 
	old_text TEXT NOT NULL, 
	created_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(variant_id) REFERENCES template_variants (id) ON DELETE CASCADE
);


-- 앱은 postgres 역할로 직접 접속하므로 RLS를 켜서 공개 API(anon 키) 접근을 막는다

ALTER TABLE public.audiences ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.history ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.option_texts ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.presets ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.seasonal_greetings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.situations ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.chips ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.notice_rows ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.template_variants ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.variant_revisions ENABLE ROW LEVEL SECURITY;
