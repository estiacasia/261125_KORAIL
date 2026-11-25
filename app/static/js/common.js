/* 공통: API 호출(CSRF), 토스트, 복사, localStorage */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const csrf = () => (document.querySelector('meta[name=csrf-token]') || {}).content || '';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function api(method, url, data) {
    const opt = { method, headers: { Accept: 'application/json' } };
    if (data !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(data); }
    if (method !== 'GET') opt.headers['X-CSRFToken'] = csrf();
    let res;
    try { res = await fetch(url, opt); } catch (e) { const err = new Error('서버에 연결할 수 없습니다.'); err.network = true; throw err; }
    let json = null;
    try { json = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) {
      const err = new Error((json && json.error && json.error.message) || `요청 실패 (${res.status})`);
      err.status = res.status; err.field = json && json.error && json.error.field; err.code = json && json.error && json.error.code;
      throw err;
    }
    return json;
  }

  let toastT;
  function toast(msg, act, fn) {
    const t = $('toast'); if (!t) return;
    $('toastMsg').textContent = msg;
    const b = $('toastAct'); b.hidden = !act; b.textContent = act || '';
    b.onclick = () => { fn && fn(); t.classList.remove('on'); };
    t.classList.add('on'); clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove('on'), act ? 5000 : 2200);
  }

  function fallbackCopy(text) {
    const ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:-1000px;opacity:0'; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (e) { /* ignore */ }
    ta.remove(); return ok;
  }
  function copy(btn, text, after) {
    const orig = btn.dataset.o || (btn.dataset.o = btn.textContent);
    const done = ok => {
      btn.textContent = ok ? '복사됨 ✓' : '복사 실패'; btn.classList.toggle('done', ok);
      clearTimeout(btn._t); btn._t = setTimeout(() => { btn.textContent = orig; btn.classList.remove('done'); }, 1500);
      if (ok && after) after();
    };
    try { navigator.clipboard.writeText(text).then(() => done(true), () => done(fallbackCopy(text))); } catch (e) { done(fallbackCopy(text)); }
  }
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };
  function mailto(to, s, b) {
    return `mailto:${encodeURIComponent(to || '').replace(/%40/g, '@')}?subject=${encodeURIComponent(s)}&body=${encodeURIComponent(String(b).replace(/\r?\n/g, '\r\n'))}`;
  }
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  window.App = { $, api, toast, copy, ls, esc, mailto, debounce };
})();
