/* AI Daily Lab — progressive enhancement. All content is in the HTML; this only adds interaction.
   Per-browser state (theme, density, read, saved) lives in localStorage and is optional. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var ROOT = (doc.body && doc.body.getAttribute('data-root')) || '';
  var $ = function (sel, el) { return (el || doc).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); };
  var reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } },
    json: function (k, dflt) { try { var v = JSON.parse(localStorage.getItem(k)); return v == null ? dflt : v; } catch (e) { return dflt; } },
    setJson: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } }
  };
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

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
  function imText(el) { return '【AI 日报】' + el.dataset.title + '\n' + el.dataset.brief + '\n' + absUrl(el.dataset.href); }

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

  /* ---------- read & saved ---------- */
  var READ_KEY = 'read', SAVED_KEY = 'saved';
  var readSet = store.json(READ_KEY, []);
  function isRead(id) { return readSet.indexOf(id) !== -1; }
  function markRead(id) {
    if (!id || isRead(id)) return;
    readSet.push(id);
    if (readSet.length > 3000) readSet = readSet.slice(-3000);
    store.setJson(READ_KEY, readSet);
    $$('[data-id="' + id + '"]').forEach(paintRead);
  }
  function paintRead(el) {
    var r = isRead(el.dataset.id);
    el.classList.toggle('is-read', r);
    var m = $('.js-read-mark', el);
    if (m) m.hidden = !r;
  }
  function savedMap() { return store.json(SAVED_KEY, {}); }
  function isSaved(id) { return Object.prototype.hasOwnProperty.call(savedMap(), id); }
  function toggleSave(el) {
    var map = savedMap(), id = el.dataset.id, on;
    if (map[id]) { delete map[id]; on = false; }
    else {
      map[id] = { t: el.dataset.title, d: el.dataset.date, c: el.dataset.cat, h: 'item/' + id + '.html', at: Date.now() };
      on = true;
    }
    store.setJson(SAVED_KEY, map);
    paintSaved();
    toast(on ? '已收藏' : '已取消收藏');
  }
  function paintSaved() {
    var map = savedMap(), n = Object.keys(map).length;
    $$('.js-save').forEach(function (b) {
      var host = b.closest('[data-id]');
      var on = !!(host && map[host.dataset.id]);
      b.setAttribute('aria-pressed', String(on));
      var label = $('.js-save-label', b);
      if (label) label.textContent = on ? '已收藏' : '收藏';
    });
    $$('.js-saved-count').forEach(function (c) { c.textContent = n > 99 ? '99+' : String(n); c.hidden = n === 0; });
  }
  $$('[data-id]').forEach(paintRead);
  paintSaved();
  var detail = $('.js-detail');
  if (detail) markRead(detail.dataset.id);
  window.addEventListener('storage', function (e) {
    if (e.key === SAVED_KEY) paintSaved();
    if (e.key === READ_KEY) { readSet = store.json(READ_KEY, []); $$('[data-id]').forEach(paintRead); }
  });

  /* ---------- clicks: copy, save, read ---------- */
  doc.addEventListener('click', function (ev) {
    var link = ev.target.closest('.item-title a');
    if (link) { var it = link.closest('[data-id]'); if (it) markRead(it.dataset.id); }
    var t = ev.target.closest('button');
    if (!t) return;
    var host = t.closest('[data-href]');
    if (t.classList.contains('js-save') && host) toggleSave(host);
    else if (t.classList.contains('js-copy-link') && host) copy(absUrl(host.dataset.href), '已复制链接');
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

  /* ---------- search palette ---------- */
  var palette = $('dialog.palette'), pInput = $('.js-palette-input'), pResults = $('.js-palette-results'), pCount = $('.js-palette-count');
  var searchData = null, searchLoading = null, pOptions = [], pSel = 0;
  var CAT = { news: '要闻', opensource: '开源项目', tools: '工具与产品', ideas: '理念与讨论', practices: '方法与实践', research: '论文' };
  var ACT = { try: '可动手', watch: '值得关注', know: '了解即可' };

  function loadSearch() {
    if (searchData) return Promise.resolve(searchData);
    if (searchLoading) return searchLoading;
    searchLoading = fetch(ROOT + 'data/search/manifest.json').then(function (r) { return r.json(); }).then(function (m) {
      return Promise.all(m.months.map(function (mo) {
        return fetch(ROOT + 'data/search/' + mo + '.json').then(function (r) { return r.json(); });
      })).then(function (shards) {
        var items = [].concat.apply([], shards);
        items.forEach(function (x) { x._hay = (x.t + ' ' + x.s + ' ' + x.g.join(' ') + ' ' + x.d).toLowerCase(); });
        items.sort(function (a, b) { return a.d < b.d ? 1 : a.d > b.d ? -1 : b.p - a.p; });
        searchData = { items: items, dates: m.dates, tags: m.tags, experiments: m.experiments };
        return searchData;
      });
    }).catch(function (e) { searchLoading = null; throw e; });
    return searchLoading;
  }
  function highlight(text, terms) {
    var out = esc(text);
    terms.forEach(function (t) {
      if (!t) return;
      var re = new RegExp('(' + esc(t).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
      out = out.replace(re, '<mark>$1</mark>');
    });
    return out;
  }
  function normDate(q) {
    var m = q.match(/^(?:(\d{4})[-/.年])?(\d{1,2})[-/.月](\d{1,2})日?$/);
    if (!m) return null;
    return (m[1] ? m[1] + '-' : '') + ('0' + m[2]).slice(-2) + '-' + ('0' + m[3]).slice(-2);
  }
  function runSearch(q) {
    var d = searchData, groups = [];
    q = q.trim();
    if (!q) {
      groups.push({ name: '快速跳转', opts: [
        { title: '今日', sub: '最新一期日报', href: ROOT + 'index.html', side: '' },
        { title: '往期', sub: '按月历浏览全部日报', href: ROOT + 'archive.html', side: '' },
        { title: '标签', sub: '按标签浏览', href: ROOT + 'tags/index.html', side: '' },
        { title: '实验室', sub: '全部可验证实验', href: ROOT + 'experiments/index.html', side: '' },
        { title: '收藏夹', sub: '本浏览器中的收藏', href: ROOT + 'saved.html', side: '' }
      ] });
      groups.push({ name: '最近几期', opts: d.dates.slice(0, 5).map(function (x) {
        return { title: x.label, sub: x.count + ' 条', href: ROOT + 'daily/' + x.date + '.html', side: x.date };
      }) });
      return groups;
    }
    var lower = q.toLowerCase().replace(/^#/, '');
    var terms = lower.split(/\s+/).filter(Boolean);
    var nd = normDate(lower);
    if (nd) {
      var dm = d.dates.filter(function (x) { return x.date.slice(-nd.length) === nd; });
      if (dm.length) groups.push({ name: '日期', opts: dm.map(function (x) { return { title: x.label, sub: x.count + ' 条', href: ROOT + 'daily/' + x.date + '.html', side: x.date }; }) });
    }
    var tagHits = d.tags.filter(function (t) { return terms.some(function (w) { return t[0].indexOf(w) !== -1; }); }).slice(0, 4);
    if (tagHits.length) groups.push({ name: '标签', opts: tagHits.map(function (t) { return { titleHtml: highlight('#' + t[0], terms), sub: t[1] + ' 条内容', href: ROOT + 'tags/' + t[0] + '.html', side: '' }; }) });
    var scored = [];
    d.items.forEach(function (x) {
      for (var i = 0; i < terms.length; i++) if (x._hay.indexOf(terms[i]) === -1) return;
      var s = 0, tl = x.t.toLowerCase();
      terms.forEach(function (w) {
        if (tl.indexOf(w) !== -1) s += 10;
        if (x.g.indexOf(w) !== -1) s += 6;
        if (x.s.toLowerCase().indexOf(w) !== -1) s += 2;
      });
      s += x.p * 0.5;
      scored.push([s, x]);
    });
    scored.sort(function (a, b) { return b[0] - a[0] || (a[1].d < b[1].d ? 1 : -1); });
    if (scored.length) groups.push({ name: '条目', total: scored.length, opts: scored.slice(0, 20).map(function (p) {
      var x = p[1];
      return { titleHtml: highlight(x.t, terms), sub: x.d + ' · ' + CAT[x.c] + (x.a ? ' · ' + ACT[x.a] : '') + ' · ' + x.s, href: ROOT + 'item/' + x.i + '.html', side: '' };
    }) });
    var ex = d.experiments.filter(function (e) { return terms.every(function (w) { return e.title.toLowerCase().indexOf(w) !== -1; }); }).slice(0, 4);
    if (ex.length) groups.push({ name: '实验', opts: ex.map(function (e) { return { titleHtml: highlight(e.title, terms), sub: e.id.slice(0, 10) + ' · ' + e.status_label, href: ROOT + 'experiments/' + e.id + '.html', side: '' }; }) });
    return groups;
  }
  function renderPalette() {
    var q = pInput.value, groups = runSearch(q), html = '', n = 0, total = 0;
    pOptions = [];
    groups.forEach(function (g) {
      html += '<div class="palette-group" role="presentation">' + esc(g.name) + '</div>';
      g.opts.forEach(function (o) {
        var id = 'po-' + n;
        html += '<a class="palette-opt" role="option" id="' + id + '" href="' + esc(o.href) + '" aria-selected="false" data-idx="' + n + '">' +
          '<span class="po-main"><span class="po-title">' + (o.titleHtml || esc(o.title)) + '</span>' +
          (o.sub ? '<span class="po-sub">' + esc(o.sub) + '</span>' : '') + '</span>' +
          (o.side ? '<span class="po-side">' + esc(o.side) + '</span>' : '') + '</a>';
        pOptions.push(o); n++;
      });
      total += g.total || g.opts.length;
    });
    if (!n) html = '<div class="palette-empty">没有找到「' + esc(q.trim()) + '」相关的内容。可以试试项目名、模型名或标签。</div>';
    pResults.innerHTML = html;
    pCount.textContent = q.trim() ? (n ? '共 ' + total + ' 个结果' : '') : '';
    pSel = 0; selectOpt(0);
  }
  function selectOpt(i) {
    var opts = $$('.palette-opt', pResults);
    if (!opts.length) { pInput.removeAttribute('aria-activedescendant'); return; }
    pSel = (i + opts.length) % opts.length;
    opts.forEach(function (o, k) { o.setAttribute('aria-selected', String(k === pSel)); });
    pInput.setAttribute('aria-activedescendant', opts[pSel].id);
    opts[pSel].scrollIntoView({ block: 'nearest' });
  }
  function openPalette() {
    if (!palette || !palette.showModal) return;
    if (!palette.open) palette.showModal();
    pInput.value = '';
    pResults.innerHTML = '<div class="palette-empty">正在加载索引…</div>';
    pInput.focus();
    loadSearch().then(renderPalette, function () {
      pResults.innerHTML = '<div class="palette-empty">搜索索引加载失败，请稍后重试。</div>';
    });
  }
  if (palette) {
    $$('.js-search').forEach(function (b) { b.addEventListener('click', openPalette); });
    pInput.addEventListener('input', function () { if (searchData) renderPalette(); });
    pInput.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { selectOpt(pSel + 1); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp') { selectOpt(pSel - 1); ev.preventDefault(); }
      else if (ev.key === 'Enter') {
        var o = pOptions[pSel];
        if (o) { location.href = o.href; palette.close(); }
        ev.preventDefault();
      }
    });
    pResults.addEventListener('mousemove', function (ev) {
      var o = ev.target.closest('.palette-opt');
      if (o && Number(o.dataset.idx) !== pSel) selectOpt(Number(o.dataset.idx));
    });
    palette.addEventListener('click', function (ev) { if (ev.target === palette) palette.close(); });
  }

  /* ---------- saved page ---------- */
  var savedList = $('.js-saved-list');
  if (savedList) {
    var cats = {};
    try { cats = JSON.parse(savedList.dataset.categories); } catch (e) { cats = CAT; }
    var renderSaved = function () {
      var map = savedMap(), ids = Object.keys(map);
      var byDate = {};
      ids.forEach(function (id) { var x = map[id]; (byDate[x.d] = byDate[x.d] || []).push([id, x]); });
      var dates = Object.keys(byDate).sort().reverse(), html = '';
      dates.forEach(function (d) {
        html += '<section class="saved-group"><h2 class="group-title"><a href="' + ROOT + 'daily/' + esc(d) + '.html">' + esc(d) + '</a><span class="count">' + byDate[d].length + '</span></h2>';
        byDate[d].sort(function (a, b) { return b[1].at - a[1].at; }).forEach(function (p) {
          var id = p[0], x = p[1];
          html += '<div class="saved-row" data-id="' + esc(id) + '" data-href="' + esc(ROOT + x.h) + '" data-title="' + esc(x.t) + '" data-date="' + esc(x.d) + '" data-cat="' + esc(x.c || '') + '">' +
            '<div class="main"><a class="title" href="' + esc(ROOT + x.h) + '">' + esc(x.t) + '</a>' +
            '<div class="sub">' + esc(cats[x.c] || '') + '</div></div>' +
            '<button type="button" class="btn btn-sm js-save" aria-pressed="true"><span class="js-save-label">已收藏</span></button></div>';
        });
        html += '</section>';
      });
      savedList.innerHTML = html;
      $('.js-saved-empty').hidden = ids.length !== 0;
      var sum = $('.js-saved-summary');
      if (sum) sum.textContent = ids.length ? '共 ' + ids.length + ' 条 · 保存在本浏览器中' : '保存在本浏览器中';
      paintSaved();
    };
    renderSaved();
    savedList.addEventListener('click', function (ev) { if (ev.target.closest('.js-save')) setTimeout(renderSaved, 0); });
    window.addEventListener('storage', function (e) { if (e.key === SAVED_KEY) renderSaved(); });
    var exp = $('.js-export-saved');
    if (exp) exp.addEventListener('click', function () {
      var map = savedMap(), ids = Object.keys(map).sort(function (a, b) { return map[a].d < map[b].d ? 1 : -1; });
      if (!ids.length) { toast('还没有收藏'); return; }
      var lines = ['# AI 日报收藏', ''];
      ids.forEach(function (id) { var x = map[id]; lines.push('- [' + x.t + '](' + absUrl(ROOT + x.h) + ') · ' + x.d); });
      copy(lines.join('\n'), '已复制 ' + ids.length + ' 条收藏（Markdown）');
    });
    var clr = $('.js-clear-saved'), armed = false, armTimer;
    if (clr) clr.addEventListener('click', function () {
      if (!armed) { armed = true; clr.textContent = '再点一次确认清空'; armTimer = setTimeout(function () { armed = false; clr.textContent = '清空收藏'; }, 3000); return; }
      clearTimeout(armTimer); armed = false; clr.textContent = '清空收藏';
      store.setJson(SAVED_KEY, {}); renderSaved(); toast('已清空收藏');
    });
  }

  /* ---------- feed: density, filters, keyboard ---------- */
  var feed = $('.feed');
  var focused = null;

  var TEXT_INPUTS = ['text', 'search', 'email', 'url', 'tel', 'password', 'number'];
  function typingTarget(ev) {
    var el = ev.target, tag = (el.tagName || '').toLowerCase();
    if (tag === 'input') return TEXT_INPUTS.indexOf((el.type || 'text').toLowerCase()) !== -1;
    return tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }
  function anyDialogOpen() { return (help && help.open) || (palette && palette.open); }

  // Ctrl/⌘ + K works everywhere, even while typing
  doc.addEventListener('keydown', function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === 'k' || ev.key === 'K')) {
      ev.preventDefault();
      if (palette && palette.open) palette.close(); else openPalette();
    }
  });

  function globalKeys(ev) {
    if (ev.key === '?') { openHelp(); return true; }
    if (ev.key === 't') { cycleTheme(); return true; }
    if (ev.key === '/') { openPalette(); return true; }
    return false;
  }

  if (feed) {
    var items = $$('.item', feed);
    var groups = $$('.group', feed);
    var state = { cat: 'all', onlyTry: false, onlyTop: false, onlyUnread: false, tag: '' };

    var setDensity = function (d, quiet) {
      feed.setAttribute('data-density', d);
      $$('.seg [data-density]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.density === d)); });
      items.forEach(function (it) { it.classList.remove('is-expanded'); });
      store.set('density', d);
      if (!quiet) toast({ title: '只看标题', summary: '标题 + 摘要', full: '完整内容' }[d]);
    };
    $$('.seg [data-density]').forEach(function (b) { b.addEventListener('click', function () { setDensity(b.dataset.density); }); });
    var savedDensity = store.get('density');
    if (savedDensity === 'title' || savedDensity === 'full') setDensity(savedDensity, true);

    var readUrl = function () {
      var q = new URLSearchParams(location.search);
      state.cat = q.get('cat') || 'all';
      state.onlyTry = q.get('try') === '1';
      state.onlyTop = q.get('top') === '1';
      state.onlyUnread = q.get('unread') === '1';
      state.tag = q.get('tag') || '';
    };
    var writeUrl = function () {
      var q = new URLSearchParams();
      if (state.cat !== 'all') q.set('cat', state.cat);
      if (state.onlyTry) q.set('try', '1');
      if (state.onlyTop) q.set('top', '1');
      if (state.onlyUnread) q.set('unread', '1');
      if (state.tag) q.set('tag', state.tag);
      var s = q.toString();
      history.replaceState(null, '', location.pathname + (s ? '?' + s : '') + location.hash);
    };
    var setFocus = function (it) {
      if (focused) focused.classList.remove('is-focused');
      focused = it;
      if (it) {
        it.classList.add('is-focused');
        var r = it.getBoundingClientRect();
        if (r.top < 140 || r.bottom > window.innerHeight - 20) {
          window.scrollTo({ top: window.scrollY + r.top - 140, behavior: reduceMotion ? 'auto' : 'smooth' });
        }
      }
    };
    var apply = function () {
      var shown = 0, unread = 0;
      items.forEach(function (it) {
        var read = isRead(it.dataset.id);
        if (!read) unread++;
        var ok = (state.cat === 'all' || it.dataset.cat === state.cat) &&
          (!state.onlyTry || it.dataset.act === 'try') &&
          (!state.onlyTop || Number(it.dataset.imp) >= 4) &&
          (!state.onlyUnread || !read) &&
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
      var boxes = { '.js-only-try': state.onlyTry, '.js-only-top': state.onlyTop, '.js-only-unread': state.onlyUnread };
      Object.keys(boxes).forEach(function (sel) { var b = $(sel); if (b) b.checked = boxes[sel]; });
      var uc = $('.js-unread-count'); if (uc) uc.textContent = unread;
      var ns = $('.js-new-since');
      if (ns) { ns.hidden = unread === items.length || unread === 0; ns.textContent = '本期未读 ' + unread + ' 条'; }
      $$('.chip.js-tag').forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.tag === state.tag)); });
      var tf = $('.js-tag-filter');
      if (tf) { tf.hidden = !state.tag; $('.js-tag-name', tf).textContent = '#' + state.tag; }
      var st = $('.js-status');
      if (st) st.textContent = shown === items.length ? '显示全部 ' + shown + ' 条' : '显示 ' + shown + ' / ' + items.length + ' 条';
      var empty = $('.js-empty');
      if (empty) empty.hidden = shown !== 0;
      if (focused && focused.hidden) setFocus(null);
      writeUrl();
    };
    $$('.js-cats .cat-btn').forEach(function (b) { b.addEventListener('click', function () { state.cat = b.dataset.cat; apply(); }); });
    [['.js-only-try', 'onlyTry'], ['.js-only-top', 'onlyTop'], ['.js-only-unread', 'onlyUnread']].forEach(function (p) {
      var b = $(p[0]); if (b) b.addEventListener('change', function () { state[p[1]] = b.checked; apply(); });
    });
    doc.addEventListener('click', function (ev) {
      var t = ev.target.closest('.js-tag');
      if (t) { state.tag = state.tag === t.dataset.tag ? '' : t.dataset.tag; apply(); return; }
      if (ev.target.closest('.js-clear-tag')) { state.tag = ''; apply(); return; }
      if (ev.target.closest('.js-reset')) { state = { cat: 'all', onlyTry: false, onlyTop: false, onlyUnread: false, tag: '' }; apply(); }
    });
    window.addEventListener('storage', function (e) { if (e.key === READ_KEY) apply(); });
    readUrl();
    apply();

    var visibleItems = function () { return items.filter(function (it) { return !it.hidden; }); };
    var move = function (step) {
      var list = visibleItems();
      if (!list.length) return;
      var i = focused ? list.indexOf(focused) : -1;
      i = Math.max(0, Math.min(list.length - 1, i + step));
      if (!focused && step < 0) i = 0;
      setFocus(list[i]);
    };
    feed.addEventListener('click', function (ev) {
      var it = ev.target.closest('.item');
      if (it && !ev.target.closest('a, button')) setFocus(it);
    });

    doc.addEventListener('keydown', function (ev) {
      if (ev.defaultPrevented || ev.metaKey || ev.ctrlKey || ev.altKey || typingTarget(ev) || anyDialogOpen()) return;
      var tag = (ev.target.tagName || '').toLowerCase();
      switch (ev.key) {
        case 'j': move(1); break;
        case 'k': move(-1); break;
        case 'o': if (focused) { focused.classList.toggle('is-expanded'); markRead(focused.dataset.id); } break;
        case 'Enter':
          if (focused && tag !== 'a' && tag !== 'button') { markRead(focused.dataset.id); location.href = focused.dataset.href; } else return;
          break;
        case 'c': if (focused) copy(absUrl(focused.dataset.href), '已复制链接'); else return; break;
        case 's': if (focused) toggleSave(focused); else return; break;
        case '1': setDensity('title'); break;
        case '2': setDensity('summary'); break;
        case '3': setDensity('full'); break;
        default: if (!globalKeys(ev)) return;
      }
      ev.preventDefault();
    });
  } else {
    doc.addEventListener('keydown', function (ev) {
      if (ev.defaultPrevented || ev.metaKey || ev.ctrlKey || ev.altKey || typingTarget(ev) || anyDialogOpen()) return;
      if (globalKeys(ev)) ev.preventDefault();
    });
  }
})();
