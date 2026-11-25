/* 이메일·공지문 렌더링 엔진 — DOM 없이 동작하는 순수 함수.
 * app/renderer.py 와 같은 입력 → 같은 결과 (tests/fixtures/render_cases.json 으로 검증).
 * 사용: MailEngine.render(catalog, state, sig, {month, hot}) → {subject, body, subjectHtml, bodyHtml, metaHtml, tag}
 */
(function (root) {
  'use strict';
  const DOW = '일월화수목금토';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const str = v => (v === undefined || v === null ? '' : String(v));
  const pd = v => {
    v = str(v);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return null;
    const [y, m, d] = v.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null;
    return dt;
  };
  const fD = v => { const d = pd(v); return d ? `${d.getMonth() + 1}월 ${d.getDate()}일(${DOW[d.getDay()]})` : ''; };
  const fT = v => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(str(v));
    if (!m) return '';
    const h = +m[1], mi = +m[2];
    if (h > 23 || mi > 59) return '';
    return `${h < 12 ? '오전' : '오후'} ${h % 12 || 12}시${mi ? ` ${mi}분` : ''}`;
  };
  const fDT = (d, t) => [fD(d), fT(t)].filter(Boolean).join(' ');
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const LIST_PREFIX = { board: '  - ', slack: '    ◦ ', kakao: '   · ' };
  const SHUF = [['subj', '제목'], ['greet', '인사말'], ['intro', '본론 도입'], ['core', '핵심 내용'], ['close', '맺음말']];

  function defaultState() {
    return { mode: 'email', sit: { email: 'schedule', notice: 'internal' }, aud: 'ext', tone: 'formal', fmt: 'board', f: {}, chips: {},
      tg: { 'attach.email': false, 'attach.notice': false, due: false, sig: false }, v: { subj: 0, greet: 0, intro: 0, core: 0, close: 0 } };
  }
  function normalize(s) {
    const b = defaultState(); s = s || {};
    const v = { ...b.v, ...(s.v || {}) };
    Object.keys(v).forEach(k => { v[k] = parseInt(v[k], 10) || 0; });
    return { ...b, ...s, sit: { ...b.sit, ...(s.sit || {}) }, f: { ...(s.f || {}) }, tg: { ...b.tg, ...(s.tg || {}) }, v, chips: { ...(s.chips || {}) } };
  }

  function make(D, stIn, sigIn, opts) {
    opts = opts || {};
    const st = normalize(stIn);
    const sig = sigIn || {};
    const month = opts.month || (new Date().getMonth() + 1);
    const hot = opts.hot || null;
    const sitKey = () => st.sit[st.mode];
    const S = () => D[st.mode].sits[sitKey()];
    const chipKey = () => st.mode + '.' + sitKey();
    const chipsOn = () => {
      const c = st.chips[chipKey()];
      return Array.isArray(c) ? c : S().chips.filter(x => x.on).map(x => x.id);
    };
    const pick = (arr, k) => { const n = arr.length; if (!n) return ''; return arr[((st.v[k] || 0) % n + n) % n]; };
    const filled = () => (Array.isArray(st.f.cands) ? st.f.cands : []).filter(c => c && str(c.d));
    const nf = x => str(st.f[sitKey() + '.' + x]).trim();
    const nlab = x => { const d = (S().fields || []).find(d => d && typeof d === 'object' && d.k === x); return d ? d.l : x; };
    const V = (v, l, g) => v ? { t: v, kind: 'v', g } : { t: '[' + l + ']', kind: 'p' };
    const season = () => str(D.season[String(month)]);
    const sg = x => str(sig[x]).trim();

    function sigLines() {
      return [[sg('name'), sg('title')].filter(Boolean).join(' '), [sg('dept'), sg('company')].filter(Boolean).join(' | '),
        [sg('phone') && 'T. ' + sg('phone'), sg('email') && 'E. ' + sg('email')].filter(Boolean).join('  ·  ')];
    }
    function sigBlock() {
      const L = sigLines().map((x, i) => x ? `{sig${i + 1}}` : null).filter(Boolean);
      return '────────────\n' + (L.length ? L.join('\n') : '{sig0}');
    }
    function nWhen() {
      const w = S().when, d1 = nf('d1'), d2 = nf('d2');
      if (w === 'range') { const s = fDT(d1, nf('t1')); const e = d2 && d2 !== d1 ? fDT(d2, nf('t2')) : fT(nf('t2')); return s && e ? `${s} ~ ${e}` : s; }
      if (w === 'days') {
        if (!d1) return '';
        const p1 = pd(d1), p2 = pd(d2);
        if (d2 && d2 > d1 && p1 && p2) { const n = Math.round((p2 - p1) / 864e5) + 1; return `${fD(d1)} ~ ${fD(d2)} (${n}일간)`; }
        return fD(d1);
      }
      return fDT(d1, nf('t1'));
    }
    function resume() {
      const b = pd(nf('d2') || nf('d1')); if (!b) return '';
      const d = new Date(b); d.setDate(d.getDate() + 1);
      while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
      return fD(iso(d));
    }
    function R(k) {
      const f = st.f, em = st.mode === 'email';
      switch (k) {
        case 'to': { const v = str(f.to).trim(); return v ? { t: v, kind: 'v', g: 'to' } : { t: D.aud[st.aud] ? D.aud[st.aud].defTo : '', kind: 'n' }; }
        case 'proj': return V(str(f.proj).trim(), '프로젝트명', 'proj');
        case 'memo': return V(str(f['memo.' + sitKey()]).trim(), S().memoName, 'memo');
        case 'cands': {
          const c = filled(); if (!c.length) return V('', '후보 일정');
          return { t: c.length === 1 ? fDT(c[0].d, c[0].t) : c.map((x, i) => `${i + 1}) ${fDT(x.d, x.t)}`).join('\n'), kind: 'v', g: 'cands' };
        }
        case 'oldDate': return V(fD(f.oldDate), '기존 마감일', 'oldDate');
        case 'newDate': return V(fD(f.newDate), '변경 예정일', 'newDate');
        case 'when': return V(fDT(f.mDate, f.mTime), '미팅 일시', 'when');
        case 'place': return em ? V(str(f.place).trim(), '장소', 'place') : V(nf('place'), nlab('place'), 'place');
        case 'link': return V(str(f.link).trim(), '화상회의 링크', 'link');
        case 'files': return V(str(f['files.' + st.mode]).trim(), '파일명', 'files');
        case 'due': return V(fD(f.due), '회신 기한', 'due');
        case 'sender': { const n = sg('name'); if (!n) return V('', '보내는 사람'); return { t: st.aud === 'team' ? n : [sg('dept'), n].filter(Boolean).join(' '), kind: 'v', g: 'sig' }; }
        case 'issuer': return V(sg('dept') || sg('name'), '발신 부서', 'sig');
        case 'sig0': return V('', '서명 정보 입력');
        case 'sig1': case 'sig2': case 'sig3': { const t = sigLines()[+k[3] - 1]; return t ? { t, kind: 'v', g: 'sig' } : { t: '', kind: 'n' }; }
        case 'nWhen': return V(nWhen(), S().whenLabel, 'nWhen');
        case 'applyDue': return V(fD(nf('applyDue')), '신청 마감', 'applyDue');
        case 'resume': return V(resume(), '업무 재개일', 'nWhen');
        case 'content': {
          const pre = LIST_PREFIX[st.fmt] || LIST_PREFIX.board;
          const L = nf('content').split('\n').map(s => s.replace(/^\s*[-•·◦*▶■]\s*/, '').trim()).filter(Boolean);
          return L.length ? { t: L.map(x => pre + x).join('\n'), kind: 'v', g: 'content' } : { t: pre + '[' + nlab('content') + ']', kind: 'p' };
        }
        case 'nTitle': case 'target': case 'apply': case 'contact': return V(nf(k), nlab(k), k);
      }
      return null;
    }
    const has = k => { const r = R(k); return !!r && r.kind === 'v'; };
    function fill(tpl, html) {
      tpl = str(tpl).replace(/%s%/g, () => season());
      return tpl.split(/\{(\w+)\}/).map((p, i) => {
        if (i % 2 === 0) return html ? esc(p) : p;
        const r = R(p);
        if (!r) return html ? esc('{' + p + '}') : '{' + p + '}';
        if (!html) return r.t;
        if (r.kind === 'v') return `<mark data-g="${esc(r.g)}"${r.g === hot ? ' class="hot"' : ''}>${esc(r.t)}</mark>`;
        if (r.kind === 'p') return `<span class="ph">${esc(r.t)}</span>`;
        return esc(r.t);
      }).join('');
    }
    function buildEmail() {
      const s = S(), t = st.tone, a = st.aud, on = chipsOn(), P = [];
      const subj = pick(s.subj[t], 'subj');
      P.push(pick(D.greet[a][t], 'greet'));
      P.push(pick(s.intro[t], 'intro'));
      let core = pick((s.coreMulti && filled().length > 1 ? s.coreMulti : s.core)[t], 'core');
      if (sitKey() === 'remind') {
        const L = ['· 일시: {when}'], hl = has('link');
        if (has('place') || !hl) L.push('· 장소: {place}');
        if (hl) L.push('· 화상회의: {link}');
        core += '\n' + L.join('\n');
      }
      P.push(core);
      if (s.memoMode === 'opt' && has('memo')) P.push('{memo}');
      const cs = s.chips.filter(c => on.includes(c.id)).map(c => str(c[t]));
      cs.filter(x => x.includes('\n')).forEach(x => P.push(x));
      const one = cs.filter(x => !x.includes('\n')); if (one.length) P.push(one.join('\n'));
      if (st.tg['attach.email']) P.push(str(D.opt.attach[t]) + (has('files') ? '\n' + str(D.opt.files) : ''));
      if (st.tg.due) P.push(str(D.opt.due[t]));
      P.push([pick(s.closeLead[t], 'close'), pick(D.close[a][t], 'close')].filter(Boolean).join('\n'));
      if (st.tg.sig) P.push(sigBlock());
      return { s: subj, b: P.filter(Boolean).join('\n\n') };
    }
    function buildNotice() {
      const s = S(), t = st.tone, fm = st.fmt, on = chipsOn(), N = D.notice;
      const subj = pick(s.subj, 'subj');
      const greet = pick(N.greet[t], 'greet'), intro = pick(s.intro[t], 'intro'), lead = pick(N.lead[t], 'core');
      const rows = s.rows.filter(r => !r.opt || has(r.tok)).map(r => {
        const tk = '{' + r.tok + '}';
        if (fm === 'slack') return r.list ? `• *${r.l}*\n${tk}` : `• *${r.l}*: ${tk}`;
        if (fm === 'kakao') return r.list ? `▶ ${r.l}\n${tk}` : `▶ ${r.l}: ${tk}`;
        return r.list ? `■ ${r.l}\n${tk}` : `■ ${r.l}: ${tk}`;
      }).join('\n');
      const notes = s.chips.filter(c => on.includes(c.id)).map(c => str(c.text));
      if (st.tg['attach.notice']) notes.push(has('files') ? str(D.opt.nFiles) : str(D.opt.nAttach[t]));
      const close = [pick(s.closeLead[t], 'close'), pick(N.close[t], 'close')].filter(Boolean).join(' ');
      let P;
      if (fm === 'slack') P = ['*' + subj + '*', greet + ' ' + intro, rows, notes.map(n => '> ' + n).join('\n'), close];
      else if (fm === 'kakao') P = ['📢 ' + subj, greet + '\n' + intro, lead + '\n' + rows, notes.join('\n'), close, '- {issuer} -'];
      else P = [greet + '\n' + intro, lead + '\n\n' + rows, notes.join('\n'), close, '{issuer} 드림', st.tg.sig ? sigBlock() : ''];
      return { s: subj, b: P.filter(Boolean).join('\n\n') };
    }
    function tag() {
      const t = st.tone === 'formal' ? '격식' : '실무';
      return st.mode === 'email' ? `${S().name} · ${D.aud[st.aud].name} · ${t}` : `공지 · ${S().name} · ${D.notice.fmtName[st.fmt]} · ${t}`;
    }
    function meta() {
      if (st.mode === 'email') {
        const em = str(st.f.toEmail).trim();
        return `<dt>받는 사람</dt><dd>${fill('{to}', true)}${em ? ` &lt;${esc(em)}&gt;` : ''}</dd><dt>보내는 사람</dt><dd>${fill('{sender}', true)}</dd>`;
      }
      return `<dt>게시 채널</dt><dd>${esc(D.notice.fmtName[st.fmt])}</dd><dt>발신</dt><dd>${fill('{issuer}', true)}</dd>`;
    }
    return { st, R, has, fill, buildEmail, buildNotice, tag, meta, sigLines, chipsOn, S, sitKey };
  }

  function render(D, st, sig, opts) {
    const c = make(D, st, sig, opts);
    const o = c.st.mode === 'email' ? c.buildEmail() : c.buildNotice();
    return {
      subject: c.fill(o.s, false), body: c.fill(o.b, false),
      subjectHtml: c.fill(o.s, true), bodyHtml: c.fill(o.b, true),
      metaHtml: c.meta(), tag: c.tag(), template: o,
    };
  }

  const SAMPLE = {
    to: '김민수 팀장님', toEmail: '', proj: '2027 브랜드 리뉴얼',
    cands: [{ d: '2026-12-03', t: '14:00' }, { d: '2026-12-04', t: '10:00' }],
    oldDate: '2026-12-04', newDate: '2026-12-11', mDate: '2026-12-03', mTime: '14:00', place: '본사 3층 대회의실', link: '',
    'files.email': '1차_시안.pdf', 'files.notice': '', due: '2026-11-27',
    'memo.schedule': '', 'memo.request': '- 단가 견적서 (수량 500개 기준)\n- 제품 사양서 및 납품 가능 일정',
    'memo.delay': '외부 협력사의 원자재 수급이 늦어지면서 생산 일정이 1주가량 밀렸습니다.',
    'memo.remind': '- 1차 시안 리뷰\n- 일정 및 역할 분담 확정', 'memo.coop': '- 신규 랜딩 페이지 QA 인력 2명 지원\n- 12월 둘째 주 테스트 일정 공유',
    'internal.nTitle': '연말 정보보호 점검', 'internal.d1': '2026-12-07', 'internal.t1': '', 'internal.target': '전 임직원',
    'internal.content': '개인 PC 보안 프로그램 업데이트\n미사용 계정 및 공유 폴더 정리\n점검 결과는 팀별로 회신', 'internal.contact': '정보보호팀 박서준 (내선 2041)',
    'recruit.nTitle': '하반기 데이터 분석 교육', 'recruit.d1': '2026-12-10', 'recruit.t1': '14:00', 'recruit.place': '본사 5층 교육장',
    'recruit.target': '희망 임직원 (선착순 30명)', 'recruit.content': '엑셀 데이터 정리 실습\n대시보드 기초 만들기',
    'recruit.apply': '사내 포털 > 교육 신청', 'recruit.applyDue': '2026-12-04', 'recruit.contact': '인재개발팀 최유나 (내선 1123)',
    'maint.nTitle': '그룹웨어', 'maint.d1': '2026-12-06', 'maint.t1': '22:00', 'maint.d2': '2026-12-07', 'maint.t2': '06:00',
    'maint.target': '메일·전자결재 전체', 'maint.content': '서버 보안 패치 적용\n데이터베이스 정기 백업', 'maint.contact': 'IT지원팀 (내선 3000)',
    'holiday.nTitle': '창립기념일', 'holiday.d1': '2026-12-18', 'holiday.d2': '2026-12-18', 'holiday.target': '전 임직원',
    'holiday.content': '해당일 전사 휴무\n고객 문의는 업무 재개 후 순차 응대', 'holiday.contact': '경영지원팀 (내선 1000)',
  };

  const api = { render, make, normalize, defaultState, esc, fD, fT, fDT, pd, SHUF, SAMPLE };
  root.MailEngine = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
