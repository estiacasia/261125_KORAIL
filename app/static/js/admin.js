/* 문구 관리: 모드 → 상황 → 블록 트리, 변주·칩·필드·행 편집, 샘플 미리보기, 조사 규칙 경고 */
(function () {
  'use strict';
  const { $, api, toast, esc } = App;
  const E = MailEngine;
  const clone = o => JSON.parse(JSON.stringify(o));
  const JOSA = /\}\s*(은|는|이|가|을|를|과|와)(?![\p{L}\p{N}_])/gu;
  const KNOWN = new Set(['to', 'sender', 'proj', 'memo', 'cands', 'oldDate', 'newDate', 'due', 'when', 'place', 'link', 'files', 'issuer', 'sig0', 'sig1', 'sig2', 'sig3', 'nTitle', 'target', 'apply', 'contact', 'nWhen', 'applyDue', 'resume', 'content']);
  const SIG = { name: '이지은', title: '매니저', dept: '마케팅팀', company: '', phone: '010-1234-5678', email: 'jieun@example.com' };
  const BLOCK_KEY = { subj: 'subj', greet: 'greet', intro: 'intro', core: 'core', core_multi: 'core', lead: 'core', close_lead: 'close', close: 'close' };

  let tree = null, cat = null, sel = { kind: 'common', mode: 'email' }, tab = 'variants', focus = null;

  function warnings(text) {
    const w = [];
    for (const m of String(text).matchAll(JOSA)) w.push(`조사 규칙: 토큰 바로 뒤 '${m[1]}' — 받침에 따라 어색해질 수 있어요. '께', '입니다', '관련' 등으로 바꿔 주세요.`);
    for (const m of String(text).matchAll(/\{(\w+)\}/g)) if (!KNOWN.has(m[1])) w.push(`정의되지 않은 토큰 {${m[1]}} — 원문 그대로 출력됩니다.`);
    return w;
  }

  async function load() {
    const [a, c] = await Promise.all([api('GET', '/api/catalog/admin'), api('GET', '/api/catalog')]);
    tree = a.tree; delete c.rev; cat = c;
    renderTree(); renderEditor(); preview();
  }

  /* ---------- tree ---------- */
  function renderTree() {
    const btn = (s, label) => `<button type="button" data-sel='${esc(JSON.stringify(s))}' aria-current="${String(JSON.stringify(s) === JSON.stringify(selKey()))}">${esc(label)}</button>`;
    $('tree').innerHTML = ['email', 'notice'].map(m => `<h3>${m === 'email' ? '이메일' : '공지문'}</h3>` +
      btn({ kind: 'common', mode: m }, m === 'email' ? '공통 인사말·맺음말' : '공통 인사·리드·맺음') +
      tree[m].situations.map(s => btn({ kind: 'sit', id: s.id }, s.name)).join('')).join('');
  }
  const selKey = () => sel.kind === 'common' ? { kind: 'common', mode: sel.mode } : { kind: 'sit', id: sel.id };
  const curSit = () => sel.kind === 'sit' ? [...tree.email.situations, ...tree.notice.situations].find(s => s.id === sel.id) : null;
  const curMode = () => sel.kind === 'common' ? sel.mode : curSit().mode;

  /* ---------- editor ---------- */
  function groupHTML(g, gi) {
    return `<div class="grp" data-gi="${gi}"><h4><span>${esc(g.label)}</span><span class="muted">활성 ${g.variants.filter(v => v.is_active).length}개</span></h4>
      ${g.variants.map((v, i) => `<div class="var${v.is_active ? '' : ' off'}" data-vid="${v.id}">
        <textarea data-vtext aria-label="${esc(g.label)} 변주 ${i + 1}">${esc(v.text)}</textarea>
        <div class="ops"><button type="button" data-vsave>저장</button><button type="button" data-vmove="up" aria-label="위로">↑</button><button type="button" data-vmove="down" aria-label="아래로">↓</button>
        <button type="button" data-vtoggle>${v.is_active ? '비활성' : '활성화'}</button><button type="button" data-vrev>이력</button></div>
        <div class="warnbox" style="grid-column:1/-1">${warnings(v.text).map(w => `<div class="warn">${esc(w)}</div>`).join('')}</div>
      </div>`).join('')}
      <div class="var" data-new><textarea data-vtext data-newtext placeholder="새 변주 문구 (예: {proj} 관련 안내드립니다.)" aria-label="새 변주"></textarea>
        <div class="ops"><button type="button" data-vadd>+ 추가</button></div><div class="warnbox" style="grid-column:1/-1"></div></div>
    </div>`;
  }
  function groups() { return sel.kind === 'common' ? tree[sel.mode].common : curSit().groups; }

  function renderEditor() {
    const s = curSit(), mode = curMode();
    const title = sel.kind === 'common' ? (mode === 'email' ? '이메일 공통 인사말·맺음말' : '공지 공통 인사·리드·맺음') : `${mode === 'email' ? '이메일' : '공지'} · ${s.name}`;
    const tabs = sel.kind === 'common' ? [] : [['variants', '문구 변주'], ['chips', '옵션 칩'], ['fields', '입력 필드']].concat(mode === 'notice' ? [['rows', '공지 행']] : []);
    if (!tabs.some(t => t[0] === tab)) tab = 'variants';
    let h = `<h2 class="t">${esc(title)}</h2>`;
    if (tabs.length) h += `<div class="seg sectabs" role="group" aria-label="편집 항목">${tabs.map(([k, l]) => `<button type="button" data-tab="${k}" aria-pressed="${k === tab}">${l}</button>`).join('')}</div>`;
    h += '<p class="muted">토큰은 <code>{proj}</code>처럼 중괄호로 씁니다. 토큰 바로 뒤에는 은/는/이/가/을/를/과/와 대신 께·입니다·관련·건으로·까지·에·의 등을 쓰세요. <code>%s%</code>는 이번 달 계절 인사로 바뀝니다.</p>';
    if (tab === 'variants') h += groups().map(groupHTML).join('');
    else if (tab === 'chips') h += chipsHTML(s);
    else if (tab === 'fields') h += fieldsHTML(s);
    else if (tab === 'rows') h += rowsHTML(s);
    $('editor').innerHTML = h;
  }

  function chipsHTML(s) {
    const em = s.mode === 'email';
    const row = c => `<div class="grp" data-cid="${c ? c.id : ''}">
      <div class="row2"><label class="f"><span>칩 이름</span><input data-c="label" value="${esc(c ? c.label : '')}" maxlength="40"></label>
      <label class="f"><span>코드 ${c ? '<small>변경 불가</small>' : '<small>영문</small>'}</span><input data-c="code" value="${esc(c ? c.code : '')}" maxlength="30"${c ? ' disabled' : ''}></label></div>
      ${em ? `<label class="f"><span>격식 문장</span><textarea data-c="text_formal">${esc(c ? c.text_formal || '' : '')}</textarea></label>
               <label class="f"><span>실무 문장</span><textarea data-c="text_brief">${esc(c ? c.text_brief || '' : '')}</textarea></label>`
            : `<label class="f"><span>안내 문장</span><textarea data-c="text">${esc(c ? c.text || '' : '※ ')}</textarea></label>`}
      <div class="btns" style="margin-top:10px;align-items:center"><label class="chk"><input type="checkbox" data-c="default_on"${c && c.default_on ? ' checked' : ''}> 기본 ON</label>
      <span class="sp" style="flex:1"></span>${c ? '<button type="button" class="mini" data-cdel>삭제</button><button type="button" class="btn" data-csave>저장</button>' : '<button type="button" class="btn" data-cadd>칩 추가</button>'}</div>
      <div class="warnbox"></div></div>`;
    return s.chips.map(row).join('') + '<h3 class="muted" style="margin:18px 0 0">새 칩</h3>' + row(null);
  }
  function fieldsHTML(s) {
    const hint = s.mode === 'email'
      ? '이메일 상황은 공통 필드 키 목록입니다. 사용 가능: cands, oldDate, newDate, mDate, mTime, place, link (수신자명·이메일·프로젝트명·메모는 자동 포함)'
      : '각 필드: k(영문 키), l(라벨), sub(보조 설명), type(text/date/time/textarea/url), ph(placeholder), half(1이면 반폭), tok(연결 토큰). 입력값은 <code>상황.키</code>로 저장됩니다.';
    return `<p class="muted">${hint}</p><textarea class="codebox" id="fieldsJson" spellcheck="false" aria-label="입력 필드 JSON">${esc(JSON.stringify(s.fields, null, 1))}</textarea>
      <div class="btns" style="margin-top:10px"><button type="button" class="btn" id="fieldsSave">필드 저장</button></div>`;
  }
  function rowsHTML(s) {
    const tr = r => `<tr data-rid="${r ? r.id : ''}"><td><input data-r="label" value="${esc(r ? r.label : '')}" maxlength="30" aria-label="라벨"></td>
      <td><input data-r="token" value="${esc(r ? r.token : '')}" maxlength="30" aria-label="토큰"></td>
      <td><input type="checkbox" data-r="is_list"${r && r.is_list ? ' checked' : ''} aria-label="목록"></td>
      <td><input type="checkbox" data-r="is_optional"${r && r.is_optional ? ' checked' : ''} aria-label="선택"></td>
      <td><div class="btns">${r ? '<button class="mini" data-rmove="up">↑</button><button class="mini" data-rmove="down">↓</button><button class="mini" data-rsave>저장</button><button class="mini" data-rdel>삭제</button>' : '<button class="btn" data-radd>추가</button>'}</div></td></tr>`;
    return `<p class="muted">공지 본문의 개조식 행입니다. 목록=여러 줄 항목, 선택=값이 비면 행 생략. 토큰 예: nWhen, place, target, content, apply, applyDue, contact</p>
      <div class="tablewrap"><table class="grid"><thead><tr><th>라벨</th><th>토큰</th><th>목록</th><th>선택</th><th></th></tr></thead>
      <tbody>${s.rows.map(tr).join('')}</tbody><tfoot>${tr(null)}</tfoot></table></div>`;
  }

  /* ---------- preview ---------- */
  function preview() {
    if (!cat) return;
    const mode = curMode(), s = curSit();
    const D = clone(cat);
    const code = s && D[mode].sits[s.code] ? s.code : D[mode].order[0];
    const st = {
      mode, sit: { email: mode === 'email' ? code : 'schedule', notice: mode === 'notice' ? code : 'internal' },
      aud: $('pvAud').value, tone: $('pvTone').value, fmt: $('pvFmt').value, f: clone(E.SAMPLE),
      chips: {}, tg: { 'attach.email': false, 'attach.notice': false, due: false, sig: true }, v: { subj: 0, greet: 0, intro: 0, core: 0, close: 0 },
    };
    if (focus) {
      const g = focus.group, t = focus.text;
      if (g.tone) st.tone = g.tone;
      if (g.audience) st.aud = g.audience;
      st.v[BLOCK_KEY[g.block]] = 0;
      if (mode === 'email') {
        const sit = D.email.sits[code];
        if (g.situation_id === null) D[g.block][g.audience][g.tone] = [t];
        else if (g.block === 'core_multi') { sit.coreMulti = sit.coreMulti || { formal: [''], brief: [''] }; sit.coreMulti[g.tone] = [t]; }
        else {
          const key = { subj: 'subj', intro: 'intro', core: 'core', close_lead: 'closeLead' }[g.block];
          sit[key][g.tone] = [t];
          if (g.block === 'core' && code === 'schedule') st.f.cands = st.f.cands.slice(0, 1);
        }
      } else {
        const sit = D.notice.sits[code];
        if (g.situation_id === null) D.notice[g.block][g.tone] = [t];
        else if (g.block === 'subj') sit.subj = [t];
        else sit[{ intro: 'intro', close_lead: 'closeLead' }[g.block]][g.tone] = [t];
      }
      $('pvTone').value = st.tone; $('pvAud').value = st.aud;
    }
    if (tab === 'chips' && s) st.chips[mode + '.' + code] = D[mode].sits[code].chips.map(c => c.id);
    $('pvAud').hidden = mode !== 'email'; $('pvFmt').hidden = mode !== 'notice';
    try {
      const r = E.render(D, st, SIG, {});
      $('pvSubj').innerHTML = r.subjectHtml; $('pvBody').innerHTML = r.bodyHtml; $('pvTag').textContent = r.tag + (tab === 'chips' ? ' · 칩 모두 ON' : '');
    } catch (e) { $('pvBody').textContent = '미리보기를 만들 수 없습니다: ' + e.message; }
  }

  /* ---------- actions ---------- */
  async function act(fn, okMsg) {
    try {
      const r = await fn();
      if (r && r.warnings && r.warnings.length) toast(`저장했지만 확인할 점이 있어요: ${r.warnings[0]}`);
      else if (okMsg) toast(okMsg);
      await load();
    } catch (e) { toast(e.message); }
  }
  function groupOf(el) { const gi = +el.closest('[data-gi]').dataset.gi; return groups()[gi]; }

  function bind() {
    $('tree').addEventListener('click', e => {
      const b = e.target.closest('[data-sel]'); if (!b) return;
      sel = JSON.parse(b.dataset.sel); focus = null; renderTree(); renderEditor(); preview();
    });
    ['pvAud', 'pvFmt', 'pvTone'].forEach(id => $(id).addEventListener('change', () => { focus = null; preview(); }));
    const ed = $('editor');
    ed.addEventListener('focusin', e => {
      if (e.target.matches('[data-vtext]')) { focus = { group: groupOf(e.target), text: e.target.value || '(새 문구)' }; preview(); }
    });
    ed.addEventListener('input', e => {
      const t = e.target;
      if (t.matches('[data-vtext]')) {
        focus = { group: groupOf(t), text: t.value || '(새 문구)' }; preview();
        const box = t.parentElement.querySelector('.warnbox'); box.innerHTML = warnings(t.value).map(w => `<div class="warn">${esc(w)}</div>`).join('');
      } else if (t.matches('[data-c^=text]')) {
        const box = t.closest('.grp').querySelector('.warnbox'); box.innerHTML = warnings(t.value).map(w => `<div class="warn">${esc(w)}</div>`).join('');
      }
    });
    ed.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
      if (d.tab) { tab = d.tab; focus = null; renderEditor(); preview(); return; }
      const v = b.closest('[data-vid]');
      if ('vsave' in d) return act(() => api('PUT', '/api/catalog/variants/' + v.dataset.vid, { text: v.querySelector('textarea').value }), '문구를 저장했습니다.');
      if (d.vmove) return act(() => api('PATCH', '/api/catalog/variants/' + v.dataset.vid, { move: d.vmove }));
      if ('vtoggle' in d) { const on = v.classList.contains('off'); return act(() => api('PATCH', '/api/catalog/variants/' + v.dataset.vid, { is_active: on }), on ? '활성화했습니다.' : '비활성화했습니다.'); }
      if ('vrev' in d) return showRevisions(v.dataset.vid);
      if ('vadd' in d) {
        const g = groupOf(b), text = b.closest('[data-new]').querySelector('textarea').value;
        return act(() => api('POST', '/api/catalog/variants', { mode: g.mode, situation_id: g.situation_id, block: g.block, audience: g.audience, tone: g.tone, text }), '변주를 추가했습니다. 생성기 셔플 후보에 바로 포함됩니다.');
      }
      const cbox = b.closest('[data-cid]');
      if (cbox) {
        const data = {}; cbox.querySelectorAll('[data-c]').forEach(i => { data[i.dataset.c] = i.type === 'checkbox' ? i.checked : i.value; });
        if ('csave' in d) { delete data.code; return act(() => api('PUT', '/api/catalog/chips/' + cbox.dataset.cid, data), '칩을 저장했습니다.'); }
        if ('cdel' in d) { if (!confirm('이 칩을 삭제할까요?')) return; return act(() => api('DELETE', '/api/catalog/chips/' + cbox.dataset.cid), '칩을 삭제했습니다.'); }
        if ('cadd' in d) return act(() => api('POST', '/api/catalog/chips', { ...data, situation_id: sel.id }), '칩을 추가했습니다.');
      }
      if (b.id === 'fieldsSave') {
        let fields; try { fields = JSON.parse($('fieldsJson').value); } catch (err) { toast('JSON 형식이 올바르지 않습니다: ' + err.message); return; }
        return act(() => api('PUT', `/api/catalog/situations/${sel.id}/fields`, { fields }), '입력 필드를 저장했습니다.');
      }
      const tr = b.closest('[data-rid]');
      if (tr) {
        const data = {}; tr.querySelectorAll('[data-r]').forEach(i => { data[i.dataset.r] = i.type === 'checkbox' ? i.checked : i.value; });
        if ('rsave' in d) return act(() => api('PUT', '/api/catalog/rows/' + tr.dataset.rid, data), '행을 저장했습니다.');
        if (d.rmove) return act(() => api('PATCH', '/api/catalog/rows/' + tr.dataset.rid, { move: d.rmove }));
        if ('rdel' in d) { if (!confirm('이 행을 삭제할까요?')) return; return act(() => api('DELETE', '/api/catalog/rows/' + tr.dataset.rid), '행을 삭제했습니다.'); }
        if ('radd' in d) return act(() => api('POST', '/api/catalog/rows', { ...data, situation_id: sel.id }), '행을 추가했습니다.');
      }
    });
  }

  async function showRevisions(vid) {
    try {
      const { items } = await api('GET', `/api/catalog/variants/${vid}/revisions`);
      if (!items.length) { toast('수정 이력이 없습니다.'); return; }
      alert('이전 문구 (최근순)\n\n' + items.slice(0, 10).map(r => `[${r.created_at}]\n${r.old_text}`).join('\n\n'));
    } catch (e) { toast(e.message); }
  }

  bind();
  load().catch(e => { $('tree').innerHTML = `<p class="muted">불러오지 못했습니다: ${esc(e.message)}</p>`; });
})();
