/* 최근 기록 · 프리셋 패널 (서버 API, 실패 시 localStorage 대체) */
(function () {
  'use strict';
  const { $, api, toast, ls, esc } = App;
  let H = null; // hooks from generator: getState, getEdited, getCurrent, tagText, restore
  let tab = 'recent';
  let serverRecent = null;

  const fmtWhen = s => {
    const d = typeof s === 'number' ? new Date(s) : new Date(String(s).replace(' ', 'T'));
    if (isNaN(d)) return '';
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };
  const clone = o => JSON.parse(JSON.stringify(o));

  function addLocal() {
    const { s, b } = H.getOutput();
    let r = ls.get('mailgen-recent', []).filter(x => !(x.s === s && x.b === b));
    r.unshift({ id: Date.now(), s, b, ed: !!H.getEdited(), label: H.tagText(), snap: clone(H.getState()) });
    ls.set('mailgen-recent', r.slice(0, 5));
  }

  async function save(action) {
    const ed = H.getEdited();
    const payload = { state: H.getState(), sig: H.getSig(), action };
    if (ed) payload.edited = { subject: ed.s, body: ed.b };
    try {
      await api('POST', '/api/history', payload);
      await refresh();
      return true;
    } catch (e) {
      addLocal();
      serverRecent = null;
      render();
      toast(`기록을 서버에 저장하지 못해 이 브라우저에 임시 저장했습니다. (${e.message})`);
      return false;
    }
  }

  async function refresh() {
    if (tab === 'recent') {
      try { serverRecent = (await api('GET', '/api/history?limit=5')).items; } catch (e) { serverRecent = null; }
    }
    render();
  }

  let presets = [];
  async function loadPresets() {
    try { presets = (await api('GET', '/api/presets')).items; } catch (e) { presets = []; toast('프리셋을 불러오지 못했습니다.'); }
    render();
  }

  function render() {
    document.querySelectorAll('[data-lib]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lib === tab)));
    const body = $('libBody');
    if (tab === 'recent') {
      if (serverRecent) {
        body.innerHTML = serverRecent.length
          ? `<div class="list">${serverRecent.map(x => `<div class="item"><button type="button" class="go" data-rec="${x.id}"><b>${esc(x.subject)}</b><span>${esc(x.label)} · ${fmtWhen(x.created_at)}${x.is_edited ? ' · 수정본' : ''}</span></button></div>`).join('')}</div><p class="note" style="text-align:right"><a href="/history">전체 이력 보기 →</a></p>`
          : '<p class="empty">본문을 복사하거나 메일 앱으로 열면 최근 5건이 여기에 쌓입니다.</p>';
      } else {
        const r = ls.get('mailgen-recent', []);
        body.innerHTML = (r.length
          ? `<div class="list">${r.map(x => `<div class="item"><button type="button" class="go" data-lrec="${x.id}"><b>${esc(x.s)}</b><span>${esc(x.label)} · ${fmtWhen(x.id)}${x.ed ? ' · 수정본' : ''}</span></button></div>`).join('')}</div>`
          : '<p class="empty">본문을 복사하거나 메일 앱으로 열면 최근 5건이 여기에 쌓입니다.</p>') + '<p class="note">서버에 연결되지 않아 이 브라우저에 저장된 기록을 보여 줍니다.</p>';
      }
    } else {
      body.innerHTML = `<form class="save" id="presetForm"><input id="presetName" placeholder="프리셋 이름 (예: A사 월간 미팅)" aria-label="프리셋 이름" maxlength="40"><button type="submit">현재 설정 저장</button></form>` +
        (presets.length
          ? `<div class="list">${presets.map(x => `<div class="item"><button type="button" class="go" data-pre="${x.id}"><b>${esc(x.name)}</b><span>${esc(H.tagFor(x.snapshot))}</span></button><button type="button" class="x" data-predel="${x.id}" aria-label="${esc(x.name)} 삭제">×</button></div>`).join('')}</div>`
          : '<p class="empty">자주 쓰는 수신자·상황·옵션 조합을 저장해 두고 한 번에 불러오세요. (최대 20개)</p>');
    }
  }

  async function onClick(e) {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.lib) { tab = d.lib; render(); tab === 'recent' ? refresh() : loadPresets(); }
    else if (d.rec) {
      try {
        const x = await api('GET', '/api/history/' + d.rec);
        H.restore(x.snapshot, x.is_edited ? { s: x.subject, b: x.body } : null);
        toast('최근 기록을 불러왔습니다.');
      } catch (err) { toast(err.message); }
    } else if (d.lrec) {
      const x = ls.get('mailgen-recent', []).find(x => String(x.id) === d.lrec);
      if (x) { H.restore(x.snap, x.ed ? { s: x.s, b: x.b } : null); toast('최근 기록을 불러왔습니다.'); }
    } else if (d.pre) {
      const x = presets.find(x => String(x.id) === d.pre);
      if (x) { H.restore(x.snapshot, null); toast(`'${x.name}' 프리셋을 불러왔습니다.`); }
    } else if (d.predel) {
      const x = presets.find(x => String(x.id) === d.predel); if (!x) return;
      try {
        await api('DELETE', '/api/presets/' + x.id);
        presets = presets.filter(y => y !== x); render();
        toast('프리셋을 삭제했습니다.', '되돌리기', async () => {
          try { await api('POST', '/api/presets', { name: x.name, snapshot: x.snapshot }); loadPresets(); } catch (err) { toast(err.message); }
        });
      } catch (err) { toast(err.message); }
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    const name = ($('presetName').value || '').trim() || H.tagText();
    try {
      await api('POST', '/api/presets', { name, snapshot: H.getState() });
      toast('현재 설정을 프리셋으로 저장했습니다.');
      loadPresets();
    } catch (err) { toast(`프리셋을 저장하지 못했습니다. (${err.message})`); }
  }

  function init(hooks) {
    H = hooks;
    const lib = document.querySelector('.lib');
    lib.addEventListener('click', onClick);
    lib.addEventListener('submit', onSubmit);
    render();
    refresh();
  }

  window.Library = { init, save, refresh };
})();
