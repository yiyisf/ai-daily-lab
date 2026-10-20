/* AI Daily Lab — progressive enhancement. All content is in the HTML; this only adds interaction. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var $ = function (sel, el) { return (el || doc).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); };

  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } }
  };

  /* ---------- toast & clipboard ---------- */
  var toastEl = $('.toast'), toastTimer;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 1800);
  }
  function copy(text, okMsg) {
    function fallback() {
      var ta = doc.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      doc.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = doc.execCommand('copy'); } catch (e) { ok = false; }
      doc.body.removeChild(ta);
      toast(ok ? okMsg : '复制失败，请手动复制');
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { toast(okMsg); }, fallback);
    } else { fallback(); }
  }
  function absUrl(href) { try { return new URL(href, location.href).href; } catch (e) { return href; } }
  function imText(el) {
    return '【AI 日报】' + el.dataset.title + '\n' + el.dataset.brief + '\n' + absUrl(el.dataset.href);
  }

  /* ---------- theme ---------- */
  var THEMES = ['system', 'light', 'dark'], THEME_LABEL = { system: '跟随系统', light: '浅色', dark: '深色' };
  function applyTheme(pref) {
    root.setAttribute('data-theme-pref', pref);
    if (pref === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', pref);
    store.set('theme', pref);
  }
  function cycleTheme() {
    var cur = root.getAttribute('data-theme-pref') || 'system';
    var next = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    applyTheme(next);
    toast('主题：' + THEME_LABEL[next]);
  }
  $$('.js-theme').forEach(function (b) { b.addEventListener('click', cycleTheme); });

  /* ---------- help dialog ---------- */
  var help = $('dialog.help');
  function openHelp() { if (help && help.showModal && !help.open) help.showModal(); }
  $$('.js-help').forEach(function (b) { b.addEventListener('click', openHelp); });

  /* ---------- copy actions (cards, detail page, tldr) ---------- */
  doc.addEventListener('click', function (ev) {
    var t = ev.target.closest('button');
    if (!t) return;
    var host = t.closest('[data-href]');
    if (t.classList.contains('js-copy-link') && host) copy(absUrl(host.dataset.href), '已复制链接');
    else if (t.classList.contains('js-copy-im') && host) copy(imText(host), '已复制，可直接粘贴到群里');
    else if (t.classList.contains('js-copy-md')) {
      var src = $('.js-md-src');
      if (src) copy(src.textContent.replace('{{URL}}', host ? absUrl(host.dataset.href) : location.href), '已复制 Markdown');
    } else if (t.classList.contains('js-copy-text')) copy(t.dataset.text, '已复制');
    else if (t.classList.contains('js-copy-tldr')) {
      var lines = ['【AI 日报】' + t.dataset.dayLabel];
      $$('.tldr li a').forEach(function (a, i) { lines.push((i + 1) + '. ' + a.textContent.trim()); });
      lines.push('完整内容：' + absUrl(t.dataset.dayHref));
      copy(lines.join('\n'), '已复制今日快报');
    }
  });

  /* ---------- feed: density, filters, keyboard ---------- */
  var feed = $('.feed');
  var focused = null;

  if (feed) {
    var items = $$('.item', feed);
    var groups = $$('.group', feed);
    var state = { cat: 'all', onlyTry: false, onlyTop: false, tag: '' };

    // density
    function setDensity(d, quiet) {
      feed.setAttribute('data-density', d);
      $$('.seg [data-density]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.density === d)); });
      items.forEach(function (it) { it.classList.remove('is-expanded'); });
      store.set('density', d);
      if (!quiet) toast({ title: '只看标题', summary: '标题 + 摘要', full: '完整内容' }[d]);
    }
    $$('.seg [data-density]').forEach(function (b) { b.addEventListener('click', function () { setDensity(b.dataset.density); }); });
    var savedDensity = store.get('density');
    if (savedDensity === 'title' || savedDensity === 'full') setDensity(savedDensity, true);

    // filters <-> URL
    function readUrl() {
      var q = new URLSearchParams(location.search);
      state.cat = q.get('cat') || 'all';
      state.onlyTry = q.get('try') === '1';
      state.onlyTop = q.get('top') === '1';
      state.tag = q.get('tag') || '';
    }
    function writeUrl() {
      var q = new URLSearchParams();
      if (state.cat !== 'all') q.set('cat', state.cat);
      if (state.onlyTry) q.set('try', '1');
      if (state.onlyTop) q.set('top', '1');
      if (state.tag) q.set('tag', state.tag);
      var s = q.toString();
      history.replaceState(null, '', location.pathname + (s ? '?' + s : '') + location.hash);
    }
    function apply() {
      var shown = 0;
      items.forEach(function (it) {
        var ok = (state.cat === 'all' || it.dataset.cat === state.cat) &&
          (!state.onlyTry || it.dataset.act === 'try') &&
          (!state.onlyTop || Number(it.dataset.imp) >= 4) &&
          (!state.tag || (' ' + it.dataset.tags + ' ').indexOf(' ' + state.tag + ' ') !== -1);
        it.hidden = !ok;
        if (ok) shown++;
      });
      groups.forEach(function (g) {
        var n = $$('.item:not([hidden])', g).length;
        g.hidden = n === 0;
        var c = $('.group-title .count', g);
        if (c) c.textContent = n;
      });
      $$('.js-cats .cat-btn').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.cat === state.cat)); });
      var tryBox = $('.js-only-try'), topBox = $('.js-only-top');
      if (tryBox) tryBox.checked = state.onlyTry;
      if (topBox) topBox.checked = state.onlyTop;
      $$('.chip.js-tag').forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.tag === state.tag)); });
      var tf = $('.js-tag-filter');
      if (tf) { tf.hidden = !state.tag; $('.js-tag-name', tf).textContent = '#' + state.tag; }
      var st = $('.js-status');
      if (st) st.textContent = shown === items.length ? '显示全部 ' + shown + ' 条' : '显示 ' + shown + ' / ' + items.length + ' 条';
      var empty = $('.js-empty');
      if (empty) empty.hidden = shown !== 0;
      if (focused && focused.hidden) setFocus(null);
      writeUrl();
    }
    $$('.js-cats .cat-btn').forEach(function (b) {
      b.addEventListener('click', function () { state.cat = b.dataset.cat; apply(); });
    });
    var tryBox = $('.js-only-try'), topBox = $('.js-only-top');
    if (tryBox) tryBox.addEventListener('change', function () { state.onlyTry = tryBox.checked; apply(); });
    if (topBox) topBox.addEventListener('change', function () { state.onlyTop = topBox.checked; apply(); });
    doc.addEventListener('click', function (ev) {
      var t = ev.target.closest('.js-tag');
      if (t) { state.tag = state.tag === t.dataset.tag ? '' : t.dataset.tag; apply(); return; }
      if (ev.target.closest('.js-clear-tag')) { state.tag = ''; apply(); return; }
      if (ev.target.closest('.js-reset')) { state = { cat: 'all', onlyTry: false, onlyTop: false, tag: '' }; apply(); }
    });
    readUrl();
    apply();

    // keyboard focus
    function visibleItems() { return items.filter(function (it) { return !it.hidden; }); }
    function setFocus(it) {
      if (focused) focused.classList.remove('is-focused');
      focused = it;
      if (it) {
        it.classList.add('is-focused');
        var r = it.getBoundingClientRect();
        if (r.top < 140 || r.bottom > window.innerHeight - 20) {
          window.scrollTo({ top: window.scrollY + r.top - 140, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
        }
      }
    }
    function move(step) {
      var list = visibleItems();
      if (!list.length) return;
      var i = focused ? list.indexOf(focused) : -1;
      i = Math.max(0, Math.min(list.length - 1, i + step));
      if (!focused && step < 0) i = 0;
      setFocus(list[i]);
    }
    feed.addEventListener('click', function (ev) {
      var it = ev.target.closest('.item');
      if (it && !ev.target.closest('a, button')) setFocus(it);
    });

    doc.addEventListener('keydown', function (ev) {
      if (ev.defaultPrevented || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      var tag = (ev.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || ev.target.isContentEditable) return;
      if (help && help.open) return;
      switch (ev.key) {
        case 'j': move(1); break;
        case 'k': move(-1); break;
        case 'o': if (focused) focused.classList.toggle('is-expanded'); break;
        case 'Enter':
          if (focused && tag !== 'a' && tag !== 'button') location.href = focused.dataset.href;
          else return;
          break;
        case 'c': if (focused) copy(absUrl(focused.dataset.href), '已复制链接'); else return; break;
        case '1': setDensity('title'); break;
        case '2': setDensity('summary'); break;
        case '3': setDensity('full'); break;
        default: return globalKeys(ev);
      }
      ev.preventDefault();
    });
  } else {
    doc.addEventListener('keydown', function (ev) {
      if (ev.defaultPrevented || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      var tag = (ev.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || ev.target.isContentEditable) return;
      if (help && help.open) return;
      globalKeys(ev);
    });
  }

  function globalKeys(ev) {
    if (ev.key === '?') { openHelp(); ev.preventDefault(); }
    else if (ev.key === 't') { cycleTheme(); ev.preventDefault(); }
  }
})();
