/* 생성기 화면: 폼 · 미리보기 · 칩 · 토글 · 직접 수정 · 복사 · mailto (아티팩트 v2 UI 로직 이식) */
(function () {
  'use strict';
  const { $, api, toast, copy, ls, esc, mailto, debounce } = App;
  const E = MailEngine;
  const boot = JSON.parse($('boot').textContent);
  const SET = boot.settings;
  const clone = o => JSON.parse(JSON.stringify(o));
  const LIMIT = { to: 50, proj: 100, toEmail: 200 };

  let D = null;
  const DEF = () => ({
    mode: SET.default_mode || 'email', sit: { email: 'schedule', notice: 'internal' }, tone: SET.default_tone || 'formal',
    aud: SET.default_audience || 'ext', fmt: SET.default_channel || 'board', f: clone(E.SAMPLE), chips: {},
    tg: { 'attach.email': true, 'attach.notice': false, due: false, sig: true }, v: { subj: 0, greet: 0, intro: 0, core: 0, close: 0 },
  });
  const norm = s => { const b = DEF(); s = s || {}; return { ...b, ...s, sit: { ...b.sit, ...(s.sit || {}) }, f: { ...b.f, ...(s.f || {}) }, tg: { ...b.tg, ...(s.tg || {}) }, v: { ...b.v, ...(s.v || {}) }, chips: { ...(s.chips || {}) } }; };
  let st = norm(ls.get('mailgen-v2', null));
  let sig = { ...ls.get('mailgen-sig', {}), ...(SET.sig || {}) };
  ls.set('mailgen-sig', sig);
  let cur = { s: '', b: '' }, ed = null, hot = null, hotT;

  const sitKey = () => st.sit[st.mode];
  const S = () => D[st.mode].sits[sitKey()];
  const chipKey = () => st.mode + '.' + sitKey();
  const chipsOn = () => st.chips[chipKey()] || S().chips.filter(c => c.on).map(c => c.id);
  const sigLines = () => E.make(D, st, sig).sigLines();
  const tagFor = snap => { try { return E.render(D, norm(snap), sig).tag; } catch (e) { return ''; } };

  function fixState() {
    ['email', 'notice'].forEach(m => { if (!D[m].sits[st.sit[m]]) st.sit[m] = D[m].order[0]; });
    if (!D.aud[st.aud]) st.aud = Object.keys(D.aud)[0];
    if (!D.notice.fmtName[st.fmt]) st.fmt = 'board';
    if (!['formal', 'brief'].includes(st.tone)) st.tone = 'formal';
    if (!['email', 'notice'].includes(st.mode)) st.mode = 'email';
  }

  /* ---------- catalog ---------- */
  async function loadCatalog() {
    const cached = ls.get('mailgen-catalog', null);
    if (cached && cached.rev === boot.rev && cached.data) return cached.data;
    try {
      const c = await api('GET', '/api/catalog');
      const rev = c.rev; delete c.rev;
      ls.set('mailgen-catalog', { rev, data: c });
      return c;
    } catch (e) {
      if (cached && cached.data) { toast('서버에 연결하지 못해 저장된 문구로 표시합니다.'); return cached.data; }
      throw e;
    }
  }

  /* ---------- form ---------- */
  function one(d) {
    if (d.type === 'cands') return candsHTML();
    const id = 'f_' + d.k.replace(/\W/g, '_'), v = esc(st.f[d.k] || '');
    const max = d.type === 'textarea' ? 2000 : (LIMIT[d.k] || (/\.nTitle$/.test(d.k) ? 100 : 200));
    const list = d.k === 'to' ? ' list="dlContacts"' : d.k === 'proj' ? ' list="dlProjects"' : '';
    const a = `id="${id}" data-k="${esc(d.k)}" data-tok="${esc(d.tok || d.k)}" placeholder="${esc(d.ph || '')}" maxlength="${max}"${list}`;
    return `<label class="f" for="${id}"><span>${esc(d.l)}${d.sub ? ` <small>${esc(d.sub)}</small>` : ''}</span>${d.type === 'textarea' ? `<textarea ${a}>${v}</textarea>` : `<input type="${esc(d.type || 'text')}" ${a} value="${v}" autocomplete="off">`}</label>`;
  }
  function fieldsHTML(defs) {
    let h = '', i = 0;
    while (i < defs.length) {
      const d = defs[i];
      if (d.half && defs[i + 1] && defs[i + 1].half) { h += `<div class="row2">${one(d)}${one(defs[i + 1])}</div>`; i += 2; }
      else { h += one(d); i++; }
    }
    return h;
  }
  function candsHTML() {
    const c = st.f.cands = st.f.cands && st.f.cands.length ? st.f.cands : [{ d: '', t: '' }];
    return `<div class="f"><span>후보 일정 <small>최대 3개</small></span>${c.map((x, i) => `<div class="cand"><b>${i + 1}</b><input type="date" data-ci="${i}" data-cf="d" value="${esc(x.d)}" aria-label="후보 ${i + 1} 날짜"><input type="time" data-ci="${i}" data-cf="t" value="${esc(x.t)}" aria-label="후보 ${i + 1} 시간">${c.length > 1 ? `<button type="button" class="x" data-crm="${i}" aria-label="후보 ${i + 1} 삭제">×</button>` : '<span></span>'}</div>`).join('')}${c.length < 3 ? '<button type="button" class="add" data-cadd>+ 후보 일정 추가</button>' : ''}</div>`;
  }
  function buildDyn() {
    const M = D[st.mode], s = S();
    $('sitSeg').innerHTML = M.order.map(k => `<button type="button" data-sit="${esc(k)}">${esc(M.sits[k].name)}</button>`).join('');
    let defs;
    if (st.mode === 'email') {
      const F = D.emailFields;
      defs = ['to', 'toEmail', 'proj'].map(k => ({ k, ...F[k] }));
      s.fields.forEach(k => defs.push(k === 'cands' ? { type: 'cands' } : { k, ...F[k] }));
      defs.push({ k: 'memo.' + sitKey(), l: s.memoLabel, sub: s.memoMode === 'chip' ? '칩으로 포함 여부 선택' : s.memoSub, ph: s.memoPh, type: 'textarea', tok: 'memo' });
    } else defs = s.fields.map(d => ({ ...d, k: sitKey() + '.' + d.k, tok: d.tok || d.k }));
    $('fields').innerHTML = fieldsHTML(defs);
    $('chips').innerHTML = s.chips.map(c => `<button type="button" data-chip="${esc(c.id)}">${esc(c.label)}</button>`).join('');
    syncUI();
  }
  function syncUI() {
    const em = st.mode === 'email', on = chipsOn();
    const set = (sel, attr, val) => document.querySelectorAll(sel).forEach(b => b.setAttribute('aria-pressed', String(b.dataset[attr] === val)));
    set('[data-mode]', 'mode', st.mode); set('[data-sit]', 'sit', sitKey()); set('[data-aud]', 'aud', st.aud);
    set('[data-tone]', 'tone', st.tone); set('[data-fmt]', 'fmt', st.fmt);
    document.querySelectorAll('[data-chip]').forEach(b => b.setAttribute('aria-pressed', String(on.includes(b.dataset.chip))));
    $('audWrap').hidden = !em; $('fmtWrap').hidden = em; $('tgDue').hidden = !em;
    const tk = k => k === 'attach' ? 'attach.' + st.mode : k; $('filesIn').dataset.k = 'files.' + st.mode;
    document.querySelectorAll('[data-tg]').forEach(i => { i.checked = !!st.tg[tk(i.dataset.tg)]; });
    document.querySelectorAll('[data-show]').forEach(x => { x.hidden = !st.tg[tk(x.dataset.show)]; });
    document.querySelectorAll('.tgx [data-k]').forEach(i => { if (document.activeElement !== i) i.value = st.f[i.dataset.k] || ''; });
    document.querySelectorAll('[data-sig]').forEach(i => { if (document.activeElement !== i) i.value = sig[i.dataset.sig] || ''; });
    $('sigSum').textContent = sigLines().filter(Boolean).slice(0, 2).join(' · ') || '아직 입력 전';
  }

  /* ---------- preview ---------- */
  $('shuf').insertAdjacentHTML('beforeend', E.SHUF.map(([k, l]) => `<button type="button" data-shuf="${k}" title="${l}만 다른 표현으로 바꾸기">${l}</button>`).join(''));
  const HINT = $('hint').textContent;
  function mailHref() {
    const s = ed ? ed.s : cur.s, b = ed ? ed.b : cur.b, to = st.mode === 'email' ? (st.f.toEmail || '').trim() : '';
    return mailto(to, s, b);
  }
  function updateHint() {
    const b = ed ? ed.b : cur.b;
    $('hint').textContent = b.length > 2000 ? `본문이 ${b.length.toLocaleString()}자입니다. 일부 메일 앱은 긴 본문을 자를 수 있어요. 잘리면 본문 복사를 이용하세요.` : HINT;
  }
  function render() {
    const r = E.render(D, st, sig, { hot });
    cur = { s: r.subject, b: r.body };
    $('subj').innerHTML = r.subjectHtml; $('body').innerHTML = r.bodyHtml;
    $('tag').textContent = r.tag; $('meta').innerHTML = r.metaHtml;
    const Ed = !!ed;
    $('subj').hidden = Ed; $('eSubj').hidden = !Ed; $('body').hidden = Ed; $('eBody').hidden = !Ed; $('banner').hidden = !Ed; $('editBtn').hidden = Ed;
    $('dice').disabled = Ed; document.querySelectorAll('[data-shuf]').forEach(b => { b.disabled = Ed; });
    $('mailto').href = mailHref(); updateHint();
    ls.set('mailgen-v2', st);
  }
  function grow() { const t = $('eBody'); t.style.height = 'auto'; t.style.height = Math.max(420, t.scrollHeight + 4) + 'px'; }
  function startEdit() { ed = { s: cur.s, b: cur.b }; $('eSubj').value = ed.s; $('eBody').value = ed.b; render(); grow(); $('eBody').focus(); }
  function setHot(g) { hot = g; clearTimeout(hotT); hotT = setTimeout(() => { hot = null; document.querySelectorAll('mark.hot').forEach(m => m.classList.remove('hot')); }, 1500); }

  function restore(snap, edit) {
    st = norm(clone(snap)); fixState(); ed = edit || null;
    if (ed) { $('eSubj').value = ed.s; $('eBody').value = ed.b; }
    buildDyn(); render(); if (ed) grow();
  }

  /* ---------- autocomplete (주소록·프로젝트) ---------- */
  const contactMap = new Map();
  const fetchContacts = debounce(async q => {
    try {
      const { items } = await api('GET', '/api/contacts?q=' + encodeURIComponent(q || ''));
      items.forEach(c => contactMap.set(c.display_name, c));
      $('dlContacts').innerHTML = items.map(c => `<option value="${esc(c.display_name)}">${esc([c.company, c.email].filter(Boolean).join(' · '))}</option>`).join('');
    } catch (e) { /* 자동완성 실패는 무시 */ }
  }, 200);
  const fetchProjects = debounce(async q => {
    try {
      const { items } = await api('GET', '/api/projects?q=' + encodeURIComponent(q || ''));
      $('dlProjects').innerHTML = items.map(p => `<option value="${esc(p.name)}"></option>`).join('');
    } catch (e) { /* ignore */ }
  }, 200);
  function applyContact(name) {
    const c = contactMap.get(name); if (!c) return;
    if (c.email) { st.f.toEmail = c.email; const el = document.querySelector('[data-k="toEmail"]'); if (el) el.value = c.email; }
    if (c.default_audience && D.aud[c.default_audience]) st.aud = c.default_audience;
    syncUI();
  }

  /* ---------- signature sync ---------- */
  let sigWarned = false;
  const pushSig = debounce(async () => {
    try { await api('PUT', '/api/settings', { sig }); sigWarned = false; }
    catch (e) { if (!sigWarned) { toast('서명을 서버에 저장하지 못했습니다. 이 브라우저에는 보관됩니다.'); sigWarned = true; } }
  }, 600);

  /* ---------- events ---------- */
  function bind() {
    $('modes').addEventListener('click', e => { const b = e.target.closest('[data-mode]'); if (!b || b.dataset.mode === st.mode) return; st.mode = b.dataset.mode; buildDyn(); render(); });
    $('form').addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
      if (d.sit) { st.sit[st.mode] = d.sit; buildDyn(); render(); }
      else if (d.aud) { st.aud = d.aud; syncUI(); render(); }
      else if (d.tone) { st.tone = d.tone; syncUI(); render(); }
      else if (d.fmt) { st.fmt = d.fmt; syncUI(); render(); }
      else if (d.chip) { const l = [...chipsOn()], i = l.indexOf(d.chip); i < 0 ? l.push(d.chip) : l.splice(i, 1); st.chips[chipKey()] = l; syncUI(); render(); }
      else if ('cadd' in d) { if (st.f.cands.length >= 3) return; st.f.cands.push({ d: '', t: '' }); buildDyn(); render(); const n = document.querySelectorAll('[data-ci][data-cf=d]'); n[n.length - 1].focus(); }
      else if (d.crm) { st.f.cands.splice(+d.crm, 1); buildDyn(); render(); }
      else if (b.id === 'clear') {
        const prev = clone(st.f);
        Object.keys(st.f).forEach(k => { st.f[k] = k === 'cands' ? [{ d: '', t: '' }] : ''; });
        buildDyn(); render(); toast('입력값을 모두 지웠습니다.', '되돌리기', () => { st.f = prev; buildDyn(); render(); });
      }
    });
    $('form').addEventListener('input', e => {
      const t = e.target, d = t.dataset;
      if (d.k) {
        st.f[d.k] = t.value; setHot(d.tok || d.k);
        if (d.k === 'to') { applyContact(t.value); fetchContacts(t.value); }
        if (d.k === 'proj') fetchProjects(t.value);
        render();
      } else if (d.ci !== undefined) { st.f.cands[+d.ci][d.cf] = t.value; setHot('cands'); render(); }
      else if (d.sig) { sig[d.sig] = t.value; ls.set('mailgen-sig', sig); setHot('sig'); pushSig(); syncUI(); render(); }
    });
    $('form').addEventListener('focusin', e => {
      const k = e.target.dataset && e.target.dataset.k;
      if (k === 'to') fetchContacts(e.target.value); else if (k === 'proj') fetchProjects(e.target.value);
    });
    $('form').addEventListener('change', e => { const d = e.target.dataset; if (d.tg) { st.tg[d.tg === 'attach' ? 'attach.' + st.mode : d.tg] = e.target.checked; syncUI(); render(); } });

    $('dice').addEventListener('click', () => { Object.keys(st.v).forEach(k => { st.v[k] += 1 + Math.floor(Math.random() * 2); }); render(); });
    $('shuf').addEventListener('click', e => { const b = e.target.closest('[data-shuf]'); if (b && !b.disabled) { st.v[b.dataset.shuf]++; setHot(null); render(); } });
    $('editBtn').addEventListener('click', startEdit);
    $('resetBtn').addEventListener('click', () => { ed = null; render(); toast('자동 생성 문구로 되돌렸습니다.'); });
    $('eSubj').addEventListener('input', e => { ed.s = e.target.value; $('mailto').href = mailHref(); });
    $('eBody').addEventListener('input', e => { ed.b = e.target.value; grow(); $('mailto').href = mailHref(); updateHint(); });
    $('cS').addEventListener('click', e => copy(e.currentTarget, ed ? ed.s : cur.s));
    $('cB').addEventListener('click', e => copy(e.currentTarget, ed ? ed.b : cur.b, async () => {
      if (await Library.save('copy')) toast('본문을 복사하고 최근 기록에 저장했습니다.');
    }));
    $('mailto').addEventListener('click', () => { Library.save('mailto'); });
  }

  async function openFromQuery() {
    const q = new URLSearchParams(location.search);
    try {
      if (q.get('history')) {
        const x = await api('GET', '/api/history/' + encodeURIComponent(q.get('history')));
        restore(x.snapshot, x.is_edited ? { s: x.subject, b: x.body } : null); toast('이력을 불러왔습니다.');
      } else if (q.get('preset')) {
        const x = await api('GET', '/api/presets/' + encodeURIComponent(q.get('preset')));
        restore(x.snapshot, null); toast(`'${x.name}' 프리셋을 불러왔습니다.`);
      } else return;
    } catch (e) { toast(e.message); }
    history.replaceState(null, '', location.pathname);
  }

  async function init() {
    try { D = await loadCatalog(); }
    catch (e) { $('fields').innerHTML = `<p class="empty">문구 데이터를 불러오지 못했습니다. ${esc(e.message)}<br>서버에서 <code>flask seed</code>를 실행했는지 확인해 주세요.</p>`; return; }
    fixState();
    if (!(sig.name || '').trim()) $('sigBox').open = true;
    bind();
    buildDyn(); render();
    Library.init({
      getState: () => clone(st), getSig: () => ({ ...sig }), getEdited: () => ed, getOutput: () => (ed ? { s: ed.s, b: ed.b } : { ...cur }),
      tagText: () => E.render(D, st, sig).tag, tagFor, restore,
    });
    openFromQuery();
  }
  init();
})();
