/* AI Daily Lab — progressive enhancement. All content is in the HTML; this only adds interaction.
   Per-browser state (theme, density, read, saved) lives in localStorage and is optional. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var ROOT = (doc.body && doc.body.getAttribute('data-root')) || '';
  var $ = function (sel, el) { return (el || doc).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); };
  var reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- motion ----------
     Same-page changes (filters, density, expand, theme) go through the View Transitions API when the browser
     has it: elements in view get a temporary name so they glide to their new place; elements that leave fade out.
     Without the API, or with reduced motion, the change is applied instantly. */
  var canVT = typeof doc.startViewTransition === 'function';
  function nearView(el) {
    if (el.hidden) return false;
    var r = el.getBoundingClientRect();
    return r.height > 0 && r.bottom > -120 && r.top < window.innerHeight + 120;
  }
  function smooth(fn, els) {
    if (!canVT || reduceMotion || doc.hidden) { fn(); return; }
    var named = [];
    (els || []).forEach(function (el) {
      if (named.length < 40 && nearView(el)) { el.style.viewTransitionName = 'vt-el-' + named.length; named.push(el); }
    });
    root.classList.add('vt-local');
    var t = doc.startViewTransition(fn);
    var done = function () { named.forEach(function (el) { el.style.viewTransitionName = ''; }); root.classList.remove('vt-local'); };
    t.finished.then(done, done);
  }
  // Pages prerendered by speculation rules run their scripts before anyone sees them: defer side effects.
  function whenActive(fn) {
    if (doc.prerendering) doc.addEventListener('prerenderingchange', fn, { once: true }); else fn();
  }
  // Inline feedback on the button that was pressed (icon briefly turns into a check).
  function flash(btn) {
    if (!btn || !btn.classList) return;
    btn.classList.remove('is-done');
    void btn.offsetWidth;
    btn.classList.add('is-done');
    clearTimeout(btn._doneTimer);
    btn._doneTimer = setTimeout(function () { btn.classList.remove('is-done'); }, 1400);
  }

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
  function copy(text, okMsg, btn) {
    function fallback() {
      var ta = doc.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      doc.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = doc.execCommand('copy'); } catch (e) { ok = false; }
      doc.body.removeChild(ta);
      if (ok) flash(btn);
      toast(ok ? okMsg : '复制失败，请手动复制');
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { flash(btn); toast(okMsg); }, fallback);
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
    smooth(function () { applyTheme(next); });
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
    if (on) $$('[data-id="' + id + '"] .js-save, .js-detail[data-id="' + id + '"] .js-save').forEach(function (b) {
      b.classList.remove('is-popped'); void b.offsetWidth; b.classList.add('is-popped');
    });
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
  if (detail) whenActive(function () { markRead(detail.dataset.id); });
  window.addEventListener('storage', function (e) {
    if (e.key === SAVED_KEY) paintSaved();
    if (e.key === READ_KEY) { readSet = store.json(READ_KEY, []); $$('[data-id]').forEach(paintRead); }
  });

  /* ---------- followed tags (per browser) ---------- */
  var FOLLOW_KEY = 'follow', followHooks = [];
  function follows() { var v = store.json(FOLLOW_KEY, []); return Array.isArray(v) ? v : []; }
  function tagsOf(el) { return (el.dataset.tags || '').split(' ').filter(Boolean); }
  function followHit(el, f) { f = f || follows(); return tagsOf(el).some(function (t) { return f.indexOf(t) !== -1; }); }
  function toggleFollow(t) {
    var f = follows(), i = f.indexOf(t), on = i === -1;
    if (on) f.push(t); else f.splice(i, 1);
    store.setJson(FOLLOW_KEY, f);
    paintFollow();
    toast(on ? '已关注 #' + t + '，日报里相关条目会高亮' : '已取消关注 #' + t);
  }
  function paintFollow() {
    var f = follows();
    $$('.js-follow').forEach(function (b) {
      var on = f.indexOf(b.dataset.tag) !== -1;
      b.setAttribute('aria-pressed', String(on));
      var l = $('.js-follow-label', b); if (l) l.textContent = on ? '已关注' : '关注这个标签';
    });
    $$('.tag-link').forEach(function (el) {
      var t = el.dataset.tag || (el.textContent || '').trim().replace(/^#/, '');
      el.classList.toggle('is-follow', f.indexOf(t) !== -1);
    });
    $$('.item[data-tags], .js-detail[data-tags]').forEach(function (el) { el.classList.toggle('is-followed', followHit(el, f)); });
    $$('.js-followed-tags').forEach(function (box) {
      box.innerHTML = f.map(function (t) {
        return '<span class="chip chip-follow"><a href="' + ROOT + 'tags/' + encodeURIComponent(t) + '.html">#' + esc(t) + '</a>' +
          '<button type="button" class="js-unfollow" data-tag="' + esc(t) + '" aria-label="取消关注 #' + esc(t) + '">×</button></span>';
      }).join('');
    });
    $$('.js-followed-panel').forEach(function (p) { p.hidden = f.length === 0; });
    $$('.js-followed-empty').forEach(function (p) { p.hidden = f.length !== 0; });
    followHooks.forEach(function (fn) { fn(f); });
  }
  doc.addEventListener('click', function (ev) {
    var b = ev.target.closest('.js-follow, .js-unfollow');
    if (b) toggleFollow(b.dataset.tag);
  });
  window.addEventListener('storage', function (e) { if (e.key === FOLLOW_KEY) paintFollow(); });

  /* ---------- AI 软技能练习记录 (per browser) ---------- */
  var PRACTICE_KEY = 'practiced';
  function practiced() { var v = store.json(PRACTICE_KEY, {}); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; }
  function paintPractice() {
    var map = practiced(), ids = Object.keys(map), byArea = {};
    ids.forEach(function (id) { var a = map[id].a; byArea[a] = (byArea[a] || 0) + 1; });
    var covered = Object.keys(byArea).length;
    $$('.practice-area').forEach(function (el) { el.classList.toggle('is-practiced', !!byArea[el.dataset.area]); });
    $$('.js-area-count').forEach(function (el) { var n = byArea[el.dataset.area] || 0; el.textContent = n ? '×' + n : ''; });
    var host = $('.js-detail');
    $$('.js-practice').forEach(function (b) {
      var on = !!(host && map[host.dataset.id]);
      b.setAttribute('aria-pressed', String(on));
      $('.js-practice-label', b).textContent = on ? '已练习' : '我练过了';
    });
    $$('.js-practice-sum').forEach(function (el) {
      el.textContent = ids.length ? '累计练习 ' + ids.length + ' 次，覆盖 ' + covered + ' / 7 个方向' : '练完点一下，记录会保存在本浏览器里';
    });
    $$('.js-practice-total').forEach(function (el) { el.textContent = ids.length ? ids.length + ' 次 · 覆盖 ' + covered + ' / 7 个方向' : ''; });
    var list = $('.js-practice-list');
    if (list) {
      var names = {};
      $$('.practice-area[data-area]').forEach(function (el) { names[el.dataset.area] = ($('small', el) || {}).textContent; });
      list.innerHTML = ids.sort(function (a, b) { return map[b].at - map[a].at; }).map(function (id) {
        var r = map[id];
        return '<li><span class="area-badge">' + esc(names[r.a] || r.a) + '</span><a href="' + ROOT + esc(r.h) + '">' + esc(r.t) + '</a>' +
          '<span class="muted">' + new Date(r.at).toLocaleDateString('zh-CN') + '</span></li>';
      }).join('');
      var empty = $('.js-practice-empty'); if (empty) empty.hidden = ids.length > 0;
    }
  }
  doc.addEventListener('click', function (ev) {
    var b = ev.target.closest('.js-practice'), host = $('.js-detail');
    if (!b || !host) return;
    var map = practiced(), id = host.dataset.id, on = !map[id];
    if (on) map[id] = { a: b.closest('[data-area]').dataset.area, t: host.dataset.title, h: 'item/' + id + '.html', at: Date.now() };
    else delete map[id];
    store.setJson(PRACTICE_KEY, map);
    paintPractice();
    if (on) { flash(b); toast('已记录练习'); } else toast('已取消练习记录');
  });
  window.addEventListener('storage', function (e) { if (e.key === PRACTICE_KEY) paintPractice(); });

  /* ---------- weekly quiz ---------- */
  $$('.js-quiz').forEach(function (qz) {
    var QUIZ_KEY = 'quiz', week = qz.dataset.week, qs = $$('.quiz-q', qz);
    var resultEl = $('.js-quiz-result', qz), resetBtn = $('.js-quiz-reset', qz);
    qz.classList.add('is-live');
    function answers() { var m = store.json(QUIZ_KEY, {}); return (m && m[week]) || {}; }
    function save(a) { var m = store.json(QUIZ_KEY, {}); if (!m || typeof m !== 'object') m = {}; m[week] = a; store.setJson(QUIZ_KEY, m); }
    function reveal(fs, choice) {
      var ans = Number(fs.dataset.answer);
      fs.classList.add('is-answered');
      fs.classList.toggle('got-it', choice === ans);
      $$('input', fs).forEach(function (i) {
        var v = Number(i.value), lab = i.closest('.quiz-opt');
        i.disabled = true;
        if (v === choice) i.checked = true;
        lab.classList.toggle('is-right', v === ans);
        lab.classList.toggle('is-wrong', v === choice && v !== ans);
      });
      $('.quiz-ans', fs).open = true;
    }
    function score() {
      var a = answers(), n = 0, right = 0;
      qs.forEach(function (fs, i) { if (a[i] != null) { n++; if (a[i] === Number(fs.dataset.answer)) right++; } });
      resultEl.textContent = n === qs.length ? '答对 ' + right + ' / ' + qs.length + (right === qs.length ? '，全对！' : '') : (n ? '已答 ' + n + ' / ' + qs.length : '');
      resetBtn.hidden = n === 0;
    }
    var saved0 = answers();
    qs.forEach(function (fs, i) { if (saved0[i] != null) reveal(fs, saved0[i]); });
    score();
    qz.addEventListener('change', function (ev) {
      var fs = ev.target.closest('.quiz-q');
      if (!fs || fs.classList.contains('is-answered')) return;
      var i = qs.indexOf(fs), c = Number(ev.target.value), a = answers();
      a[i] = c; save(a);
      smooth(function () { reveal(fs, c); score(); });
    });
    resetBtn.addEventListener('click', function () {
      save({});
      qs.forEach(function (fs) {
        fs.classList.remove('is-answered', 'got-it');
        $$('input', fs).forEach(function (i) { i.disabled = false; i.checked = false; i.closest('.quiz-opt').classList.remove('is-right', 'is-wrong'); });
        $('.quiz-ans', fs).open = false;
      });
      score();
    });
  });

  paintFollow();
  paintPractice();

  /* ---------- offline cache (service worker; https or localhost only) ---------- */
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || /^(localhost|127\.0\.0\.1)$/.test(location.hostname))) {
    whenActive(function () {
      var reg = function () { navigator.serviceWorker.register(ROOT + 'sw.js').catch(function () { /* optional */ }); };
      if (doc.readyState === 'complete') reg(); else window.addEventListener('load', reg);
    });
  }

  /* ---------- cross-page transition (old page side; the new page side is inline in <head>) ---------- */
  function itemIdOf(u) { var m = /\/item\/([^\/?#]+)\.html/.exec(u || ''); return m ? decodeURIComponent(m[1]) : null; }
  var swapNamed = null;
  window.addEventListener('pageswap', function (e) {
    if (!e.viewTransition || !e.activation || !e.activation.entry) return;
    var to = itemIdOf(e.activation.entry.url), here = itemIdOf(location.href), el = null;
    if (to && here) return;                       // item → item: plain cross-fade
    if (to) el = $('[id="' + to + '"] .item-title');
    else if (here) el = $('.js-detail h1');
    if (el && nearView(el)) { el.style.viewTransitionName = 'vt-title'; swapNamed = el; }
  });
  window.addEventListener('pageshow', function () {   // back/forward cache: clear the name we left behind
    if (swapNamed) { swapNamed.style.viewTransitionName = ''; swapNamed = null; }
  });

  /* ---------- clicks: copy, save, read ---------- */
  doc.addEventListener('click', function (ev) {
    var link = ev.target.closest('.item-title a');
    if (link) { var it = link.closest('[data-id]'); if (it) markRead(it.dataset.id); }
    var t = ev.target.closest('button');
    if (!t) return;
    var host = t.closest('[data-href]');
    if (t.classList.contains('js-save') && host) toggleSave(host);
    else if (t.classList.contains('js-copy-link') && host) copy(absUrl(host.dataset.href), '已复制链接', t);
    else if (t.classList.contains('js-copy-im') && host) copy(imText(host), '已复制，可直接粘贴到群里', t);
    else if (t.classList.contains('js-copy-md')) {
      var src = $('.js-md-src');
      if (src) copy(src.textContent.replace('{{URL}}', host ? absUrl(host.dataset.href) : location.href), '已复制 Markdown', t);
    } else if (t.classList.contains('js-copy-text')) copy(t.dataset.text, '已复制', t);
    else if (t.classList.contains('js-copy-tldr')) {
      var lines = ['【AI 日报】' + t.dataset.dayLabel];
      $$('.tldr li a').forEach(function (a, i) { lines.push((i + 1) + '. ' + a.textContent.trim()); });
      lines.push('完整内容：' + absUrl(t.dataset.dayHref));
      copy(lines.join('\n'), '已复制今日快报', t);
    }
  });

  /* ---------- search palette ---------- */
  var palette = $('dialog.palette'), pInput = $('.js-palette-input'), pResults = $('.js-palette-results'), pCount = $('.js-palette-count');
  var searchData = null, searchLoading = null, pOptions = [], pSel = 0;
  var CAT = { news: '要闻', opensource: '开源项目', tools: '工具与产品', kits: 'Skill 精选', ideas: '理念与讨论', practices: '方法与实践', skills: 'AI 软技能', research: '论文' };
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

  /* ---------- share card (1080×1350 PNG drawn on canvas) ---------- */
  var shareDlg = $('dialog.share'), shareDataEl = $('.js-share-data');
  var SHARE_INK = '#1C1917', SHARE_INK2 = '#44403C', SHARE_INK3 = '#6F6A64', SHARE_LINE = '#E7E5E4', SHARE_BG = '#FAFAF9';
  var SHARE_ACCENT = '#C2410C', SHARE_ACCENT_INK = '#9A3412', SHARE_ACCENT_SOFT = '#FFF1E8';
  var F_SANS = 'Inter, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif';
  var F_SERIF = '"Noto Serif SC", "Songti SC", serif';
  var F_MONO = '"JetBrains Mono", ui-monospace, Menlo, monospace';
  var NO_LINE_START = '，。、；：？！）」』》”’,.;:?!)%';

  function shareUrl(path) {
    var base = (doc.body && doc.body.getAttribute('data-site-url')) || '';
    return base ? base + path : absUrl(ROOT + path);
  }
  function tokens(text) { return String(text).match(/[A-Za-z0-9][A-Za-z0-9.\-_/+:#%@]*|\s+|./g) || []; }
  // Wrap text to width; CJK breaks per character, Latin per word. Returns at most maxLines lines.
  function wrap(ctx, text, width, maxLines) {
    var lines = [], line = '';
    tokens(text).forEach(function (tk) {
      var trial = line + tk;
      if (ctx.measureText(trial).width <= width || !line.trim() || (tk.length === 1 && NO_LINE_START.indexOf(tk) !== -1)) { line = trial; return; }
      lines.push(line.replace(/\s+$/, ''));
      line = tk.replace(/^\s+/, '');
      while (ctx.measureText(line).width > width && line.length > 1) {   // a single token wider than the line
        var cut = line.length - 1;
        while (cut > 1 && ctx.measureText(line.slice(0, cut)).width > width) cut--;
        lines.push(line.slice(0, cut)); line = line.slice(cut);
      }
    });
    if (line.trim()) lines.push(line);
    if (maxLines && lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      var last = lines[maxLines - 1];
      while (last.length && ctx.measureText(last + '…').width > width) last = last.slice(0, -1);
      lines[maxLines - 1] = last.replace(/[，。、；：\s]+$/, '') + '…';
    }
    return lines;
  }
  function rrect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function svgImage(inner, color, size) {
    return new Promise(function (resolve) {
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="' + color +
        '" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { resolve(null); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
  }
  function loadFonts(specs) {
    if (!doc.fonts || !doc.fonts.load) return Promise.resolve();
    var all = Promise.all(specs.map(function (s) { return doc.fonts.load(s[0], s[1]).catch(function () {}); }));
    return Promise.race([all, new Promise(function (r) { setTimeout(r, 4000); })]);
  }
  function text(ctx, str, x, y, font, color, align) {
    ctx.font = font; ctx.fillStyle = color; ctx.textAlign = align || 'left'; ctx.fillText(str, x, y);
  }
  function drawHeader(ctx, pill) {
    ctx.save();
    ctx.translate(100, 92); ctx.rotate(Math.PI / 4);
    ctx.fillStyle = SHARE_ACCENT; rrect(ctx, -13, -13, 26, 26, 5); ctx.fill();
    ctx.restore();
    text(ctx, 'AI Daily Lab', 136, 104, '700 32px ' + F_SANS, SHARE_INK);
    ctx.font = '600 24px ' + F_SANS;
    var w = ctx.measureText(pill).width + 36;
    ctx.fillStyle = SHARE_ACCENT_SOFT; rrect(ctx, 1000 - w, 72, w, 40, 20); ctx.fill();
    text(ctx, pill, 1000 - w / 2, 101, '600 24px ' + F_SANS, SHARE_ACCENT_INK, 'center');
  }
  function drawFooter(ctx, label, url) {
    var y = 1350 - 64 - 184;
    ctx.fillStyle = SHARE_LINE; ctx.fillRect(80, y - 28, 920, 2);
    text(ctx, label, 80, y + 76, '600 26px ' + F_SANS, SHARE_INK);
    ctx.font = '400 22px ' + F_MONO;
    var shown = url.replace(/^https?:\/\//, ''), maxW = 920 - 184 - 40;
    if (ctx.measureText(shown).width > maxW) {
      while (shown.length && ctx.measureText(shown + '…').width > maxW) shown = shown.slice(0, -1);
      shown += '…';
    }
    text(ctx, shown, 80, y + 116, '400 22px ' + F_MONO, SHARE_INK3);
    if (typeof window.ADLqr !== 'function') return;
    try {
      var q = window.ADLqr(url), box = 184, n = q.size + 4, px = Math.floor(box / n), off = (box - px * q.size) / 2, x0 = 1000 - box;
      ctx.fillStyle = '#FFFFFF'; rrect(ctx, x0, y, box, box, 12); ctx.fill();
      ctx.strokeStyle = SHARE_LINE; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = SHARE_INK;
      for (var yy = 0; yy < q.size; yy++) for (var xx = 0; xx < q.size; xx++)
        if (q.get(xx, yy)) ctx.fillRect(x0 + off + xx * px, y + off + yy * px, px, px);
    } catch (e) { /* URL too long for the QR encoder: keep the text link only */ }
  }
  var FOOT_TOP = 1350 - 64 - 184 - 28 - 40;   // content must end above this line

  function drawDay(ctx, d) {
    drawHeader(ctx, '第 ' + d.issue_no + ' 期');
    // overview panel: one dot per item, colored by category, sized by importance
    var cols = 8, rows = Math.ceil(d.dots.length / cols), cellH = 76;
    ctx.font = '400 18px ' + F_SANS;
    var legend = d.cats.map(function (c) { return c[1] + ' ' + c[2]; }).concat(['圆点越大越重要']);
    var lx = 0, lRows = 1;
    legend.forEach(function (l) { var w = ctx.measureText(l).width + 44; if (lx + w > 848) { lRows++; lx = 0; } lx += w; });
    var panelY = 160, panelH = 32 + 66 + 28 + rows * cellH + 12 + lRows * 32 + 24;
    ctx.fillStyle = '#FFFFFF'; rrect(ctx, 80, panelY, 920, panelH, 28); ctx.fill();
    ctx.strokeStyle = SHARE_LINE; ctx.lineWidth = 2; ctx.stroke();
    text(ctx, d.label, 116, panelY + 32 + 58, '700 60px ' + F_SERIF, SHARE_INK);
    text(ctx, d.count + ' 条' + (d.exp_count ? ' · ' + d.exp_count + ' 个实验' : ''), 964, panelY + 32 + 54, '400 22px ' + F_SANS, SHARE_INK3, 'right');
    var gy = panelY + 32 + 66 + 28, cw = 848 / cols;
    d.dots.forEach(function (dot, i) {
      var r = ({ 5: 32, 4: 27, 3: 22, 2: 18, 1: 15 })[dot[1]] || 20;
      ctx.fillStyle = d.colors[dot[0]] || SHARE_INK3;
      ctx.beginPath(); ctx.arc(116 + cw * (i % cols) + cw / 2, gy + cellH * Math.floor(i / cols) + cellH / 2, r, 0, Math.PI * 2); ctx.fill();
    });
    var ly = gy + rows * cellH + 12 + 22; lx = 116;
    legend.forEach(function (l, i) {
      ctx.font = '400 18px ' + F_SANS;
      var w = ctx.measureText(l).width + 44;
      if (lx + w > 116 + 848) { lx = 116; ly += 32; }
      var cat = d.cats[i];
      if (cat) { ctx.fillStyle = d.colors[cat[0]]; ctx.beginPath(); ctx.arc(lx + 6, ly - 6, 6, 0, Math.PI * 2); ctx.fill(); }
      text(ctx, l, cat ? lx + 20 : lx, ly, '400 18px ' + F_SANS, cat ? '#57534E' : SHARE_INK3);
      lx += w;
    });
    // three things, shrinking the type until it fits above the footer
    var top = panelY + panelH + 60;
    for (var size = 34; size >= 26; size -= 2) {
      ctx.font = '500 ' + size + 'px ' + F_SANS;
      var lh = Math.round(size * 1.5), blocks = d.tldr.map(function (t) { return wrap(ctx, t, 852, 3); });
      var h = 26 + 30 + blocks.reduce(function (a, b) { return a + b.length * lh + 28; }, 0);
      if (top + h <= FOOT_TOP || size === 26) break;
    }
    text(ctx, d.heading, 80, top + 26, '700 26px ' + F_SANS, SHARE_ACCENT_INK);
    var y = top + 26 + 30;
    blocks.forEach(function (lines, i) {
      text(ctx, String(i + 1), 80, y + lh * 0.8, '700 48px ' + F_SERIF, SHARE_ACCENT);
      lines.forEach(function (ln, j) { text(ctx, ln, 148, y + lh * 0.75 + j * lh, '500 ' + size + 'px ' + F_SANS, SHARE_INK); });
      y += lines.length * lh + 28;
    });
    drawFooter(ctx, '完整内容与配套实验', shareUrl(d.path));
  }

  // Figure on an item card: same data as the page figure, drawn at a fixed scale. Returns its height.
  function drawFigure(ctx, f, y, draw) {
    var h = 0, x = 80, W = 920;
    function t(str, xx, yy, font, color, align) { if (draw) text(ctx, str, xx, yy, font, color, align); }
    h += 34; t(f.title, x, y + 26, '700 26px ' + F_SANS, SHARE_INK);
    h += 18;
    if (f.type === 'bars') {
      var top = 0;
      f.rows.forEach(function (r) { r.values.forEach(function (v) { top = Math.max(top, v); }); });
      top = top || 1;
      if (f.series.length > 1) {
        var lx = x;
        f.series.forEach(function (s, i) {
          if (draw) { ctx.fillStyle = i ? SHARE_ACCENT : '#D6D3D1'; rrect(ctx, lx, y + h + 4, 16, 16, 4); ctx.fill(); }
          ctx.font = '400 20px ' + F_SANS;
          t(s, lx + 24, y + h + 19, '400 20px ' + F_SANS, SHARE_INK2);
          lx += 24 + ctx.measureText(s).width + 28;
        });
        h += 40;
      }
      var labelW = 250, trackW = W - labelW - 20 - 90 - 70;
      f.rows.forEach(function (r) {
        var rowH = r.values.length * 24 + 4 + 16;
        t(r.label, x, y + h + rowH / 2 + 2, '400 22px ' + F_SANS, SHARE_INK2);
        r.values.forEach(function (v, i) {
          var by = y + h + i * 24, bw = Math.max(trackW * v / top, 4), last = i === r.values.length - 1 && r.values.length > 1;
          if (draw) { ctx.fillStyle = last ? SHARE_ACCENT : '#D6D3D1'; rrect(ctx, x + labelW + 20, by, bw, 20, 4); ctx.fill(); }
          t((r.disp ? r.disp[i] : String(v)) + (f.unit || ''), x + labelW + 20 + bw + 10, by + 17, (last ? '600' : '400') + ' 18px ' + F_MONO, last ? SHARE_ACCENT_INK : SHARE_INK3);
        });
        if (r.delta) t(r.delta, x + W, y + h + rowH / 2 + 2, '600 20px ' + F_MONO, '#166534', 'right');
        h += rowH;
      });
    } else {
      var n = f.steps.length, gap = 40, bw2 = (W - gap * (n - 1)) / n, boxH = 0, subs = [];
      ctx.font = '400 20px ' + F_SANS;
      f.steps.forEach(function (s) { var l = s.sub ? wrap(ctx, s.sub, bw2 - 36, 3) : []; subs.push(l); boxH = Math.max(boxH, 18 + 34 + l.length * 30 + 18); });
      f.steps.forEach(function (s, i) {
        var bx = x + i * (bw2 + gap);
        if (draw) {
          ctx.fillStyle = SHARE_ACCENT_SOFT; rrect(ctx, bx, y + h, bw2, boxH, 14); ctx.fill();
          ctx.strokeStyle = '#FED7C3'; ctx.lineWidth = 2; ctx.stroke();
          if (i) { ctx.strokeStyle = '#A8A29E'; ctx.beginPath(); ctx.moveTo(bx - gap + 8, y + h + boxH / 2); ctx.lineTo(bx - 10, y + h + boxH / 2); ctx.stroke();
            ctx.fillStyle = '#A8A29E'; ctx.beginPath(); ctx.moveTo(bx - 8, y + h + boxH / 2); ctx.lineTo(bx - 16, y + h + boxH / 2 - 6); ctx.lineTo(bx - 16, y + h + boxH / 2 + 6); ctx.fill(); }
        }
        ctx.font = '700 26px ' + F_SANS;
        t(wrap(ctx, s.label, bw2 - 36, 1)[0], bx + 18, y + h + 18 + 26, '700 26px ' + F_SANS, SHARE_ACCENT_INK);
        subs[i].forEach(function (ln, j) { t(ln, bx + 18, y + h + 18 + 34 + 22 + j * 30, '400 20px ' + F_SANS, SHARE_INK2); });
      });
      h += boxH;
      if (f.loop) {
        if (draw) { ctx.save(); ctx.setLineDash([8, 6]); ctx.strokeStyle = '#A8A29E'; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(x + 20, y + h + 4); ctx.lineTo(x + 20, y + h + 30); ctx.lineTo(x + W - 20, y + h + 30); ctx.lineTo(x + W - 20, y + h + 4); ctx.stroke(); ctx.restore(); }
        ctx.font = '400 20px ' + F_SANS;
        var lw = ctx.measureText('↻ ' + f.loop).width + 24;
        if (draw) { ctx.fillStyle = SHARE_BG; ctx.fillRect(x + W / 2 - lw / 2, y + h + 16, lw, 28); }
        t('↻ ' + f.loop, x + W / 2, y + h + 38, '400 20px ' + F_SANS, SHARE_INK2, 'center');
        h += 50;
      }
      if (f.base) {
        h += 12;
        var bt = f.base.label + (f.base.sub ? '  ·  ' + f.base.sub : '');
        if (draw) { ctx.fillStyle = '#F5F5F4'; rrect(ctx, x, y + h, W, 56, 14); ctx.fill(); }
        ctx.font = '600 22px ' + F_SANS;
        t(wrap(ctx, bt, W - 40, 1)[0], x + W / 2, y + h + 36, '600 22px ' + F_SANS, SHARE_INK, 'center');
        h += 56;
      }
    }
    if (f.caption) { h += 34; t(f.caption, x, y + h - 6, '400 18px ' + F_SANS, SHARE_INK3); }
    return h;
  }

  function drawItem(ctx, d, iconImg) {
    drawHeader(ctx, d.label);
    var y = 196;
    if (iconImg) ctx.drawImage(iconImg, 80, y - 38, 48, 48);
    text(ctx, d.cat_name, iconImg ? 142 : 80, y, '700 30px ' + F_SANS, d.color);
    if (d.act) {
      ctx.font = '700 30px ' + F_SANS;
      var ax = (iconImg ? 142 : 80) + ctx.measureText(d.cat_name).width + 20;
      ctx.font = '600 22px ' + F_SANS;
      var aw = ctx.measureText(d.act).width + 28;
      ctx.fillStyle = '#F5F5F4'; rrect(ctx, ax, y - 30, aw, 38, 19); ctx.fill();
      text(ctx, d.act, ax + aw / 2, y - 3, '600 22px ' + F_SANS, SHARE_INK2, 'center');
    }
    // fit title + summary + body by stepping the scale down
    for (var k = 1; k >= 0.72; k -= 0.04) {
      var tSize = Math.round(56 * k), sSize = Math.round(30 * k), bSize = Math.round(28 * k);
      ctx.font = '700 ' + tSize + 'px ' + F_SERIF; var tl = wrap(ctx, d.title, 920, 4), tLh = Math.round(tSize * 1.32);
      ctx.font = '400 ' + sSize + 'px ' + F_SANS; var sl = wrap(ctx, d.summary, 920, 6), sLh = Math.round(sSize * 1.6);
      var body = [], bLh = Math.round(bSize * 1.55), bh = 0;
      ctx.font = '400 ' + bSize + 'px ' + F_SANS;
      if (d.skill) {
        body = [['较差', d.skill.bad, '#991B1B', '#FEF2F2'], ['更好', d.skill.good, '#166534', '#F0FDF4']].map(function (b) {
          return { label: b[0], color: b[2], bg: b[3], lines: wrap(ctx, b[1], 920 - 56, 5) };
        });
        bh = body.reduce(function (a, b) { return a + 40 + 30 + b.lines.length * bLh + 24 + 20; }, 0);
      } else {
        body = d.points.map(function (p) { return wrap(ctx, p, 920 - 40, 3); });
        bh = body.reduce(function (a, b) { return a + b.length * bLh + 18; }, 0);
      }
      var figH = d.figure ? drawFigure(ctx, d.figure, 0, false) + 40 : 0;
      if (d.figure && !d.skill) { body = []; bh = 0; }   // the figure replaces the bullet points
      var total = 52 + tl.length * tLh + 28 + sl.length * sLh + 40 + figH + bh;
      if (y + total <= FOOT_TOP || k < 0.75) break;
    }
    y += 52;
    tl.forEach(function (ln) { y += tLh; text(ctx, ln, 80, y - tLh * 0.24, '700 ' + tSize + 'px ' + F_SERIF, SHARE_INK); });
    y += 28;
    sl.forEach(function (ln) { y += sLh; text(ctx, ln, 80, y - sLh * 0.3, '400 ' + sSize + 'px ' + F_SANS, SHARE_INK2); });
    y += 40;
    if (d.figure) { y += drawFigure(ctx, d.figure, y, true) + 40; }
    if (d.skill) {
      body.forEach(function (b) {
        var h = 40 + 30 + b.lines.length * bLh + 24;
        ctx.fillStyle = b.bg; rrect(ctx, 80, y, 920, h, 18); ctx.fill();
        text(ctx, b.label + '的描述', 108, y + 52, '700 ' + Math.round(bSize * 0.86) + 'px ' + F_SANS, b.color);
        b.lines.forEach(function (ln, j) { text(ctx, ln, 108, y + 70 + (j + 1) * bLh - bLh * 0.3, '400 ' + bSize + 'px ' + F_SANS, SHARE_INK); });
        y += h + 20;
      });
    } else {
      body.forEach(function (lines) {
        ctx.fillStyle = d.color; ctx.beginPath(); ctx.arc(90, y + bLh * 0.5, 6, 0, Math.PI * 2); ctx.fill();
        lines.forEach(function (ln, j) { text(ctx, ln, 120, y + (j + 1) * bLh - bLh * 0.3, '400 ' + bSize + 'px ' + F_SANS, SHARE_INK); });
        y += lines.length * bLh + 18;
      });
    }
    drawFooter(ctx, '阅读全文与原始来源', shareUrl(d.path));
  }

  function drawWeek(ctx, d) {
    drawHeader(ctx, 'AI 周报');
    text(ctx, d.label + ' · ' + d.range, 80, 196, '600 26px ' + F_SANS, SHARE_ACCENT_INK);
    ctx.font = '700 54px ' + F_SERIF;
    var tl = wrap(ctx, d.title, 920, 3), y = 196 + 24;
    tl.forEach(function (ln) { y += 72; text(ctx, ln, 80, y - 14, '700 54px ' + F_SERIF, SHARE_INK); });
    // week strip: one column per day, dots stacked from the bottom
    var maxRows = Math.min(8, Math.max(1, Math.max.apply(null, d.days.map(function (x) { return Math.ceil(x.length / 4); }))));
    var panelY = y + 36, panelH = 128 + maxRows * 26;
    ctx.fillStyle = '#FFFFFF'; rrect(ctx, 80, panelY, 920, panelH, 28); ctx.fill();
    ctx.strokeStyle = SHARE_LINE; ctx.lineWidth = 2; ctx.stroke();
    var colW = 848 / 7, base = panelY + panelH - 74, names = '一二三四五六日';
    d.days.forEach(function (dots, i) {
      var cx = 116 + colW * i + colW / 2, per = 4, cell = 26;
      dots.slice(0, 32).forEach(function (dot, k) {   // rows of 4 from the bottom, like the page
        var r = ({ 5: 12, 4: 10, 3: 8, 2: 6.5, 1: 5.5 })[dot[1]] || 7;
        var row = Math.floor(k / per), col = k % per, inRow = Math.min(per, dots.length - row * per);
        var x = cx + (col - (inRow - 1) / 2) * cell, y0 = base - 14 - row * cell;
        ctx.fillStyle = d.colors[dot[0]] || SHARE_INK3; ctx.beginPath(); ctx.arc(x, y0, r, 0, Math.PI * 2); ctx.fill();
      });
      ctx.fillStyle = SHARE_LINE; ctx.fillRect(116 + colW * i + 8, base + 14, colW - 16, 2);
      text(ctx, '周' + names[i], cx, base + 52, (dots.length ? '600' : '400') + ' 22px ' + F_SANS, dots.length ? SHARE_INK2 : '#A8A29E', 'center');
    });
    var st = d.stats;
    text(ctx, st.issues + ' 期日报 · ' + st.items + ' 条 · 可动手 ' + st.try + ' 条' + (st.exps ? ' · 实验 ' + st.exps + ' 个' : ''),
         80, panelY + panelH + 52, '400 24px ' + F_SANS, SHARE_INK3);
    var top = panelY + panelH + 100;
    for (var size = 32; size >= 26; size -= 2) {
      ctx.font = '500 ' + size + 'px ' + F_SANS;
      var lh = Math.round(size * 1.45), blocks = d.themes.map(function (t) { return wrap(ctx, t, 852, 2); });
      var h = 26 + 26 + blocks.reduce(function (a, b) { return a + b.length * lh + 20; }, 0);
      if (top + h <= FOOT_TOP || size === 26) break;
    }
    text(ctx, '本周主线', 80, top + 26, '700 26px ' + F_SANS, SHARE_ACCENT_INK);
    var yy = top + 26 + 26;
    blocks.forEach(function (lines, i) {
      text(ctx, String(i + 1), 80, yy + lh * 0.8, '700 40px ' + F_SERIF, SHARE_ACCENT);
      lines.forEach(function (ln, j) { text(ctx, ln, 140, yy + lh * 0.75 + j * lh, '500 ' + size + 'px ' + F_SANS, SHARE_INK); });
      yy += lines.length * lh + 20;
    });
    drawFooter(ctx, '完整周报与本周日报', shareUrl(d.path));
  }

  function renderShare(d) {
    var sample = JSON.stringify(d) + 'AI Daily Lab 第期条个实验圆点越大越重要完整内容与配套实验阅读全文与原始来源较差更好的描述0123456789…';
    var fonts = [['700 60px "Noto Serif SC"', sample], ['700 32px Inter', sample], ['500 34px "Noto Sans SC"', sample],
                 ['400 30px "Noto Sans SC"', sample], ['700 30px "Noto Sans SC"', sample], ['400 22px "JetBrains Mono"', 'abc']];
    return Promise.all([loadFonts(fonts), d.icon ? svgImage(d.icon, d.color, 96) : Promise.resolve(null)]).then(function (r) {
      var c = doc.createElement('canvas');
      c.width = 1080; c.height = 1350;
      var ctx = c.getContext('2d');
      ctx.fillStyle = SHARE_BG; ctx.fillRect(0, 0, 1080, 1350);
      ctx.textBaseline = 'alphabetic';
      if (d.kind === 'day') drawDay(ctx, d); else if (d.kind === 'week') drawWeek(ctx, d); else drawItem(ctx, d, r[1]);
      return new Promise(function (resolve, reject) { c.toBlob(function (b) { b ? resolve(b) : reject(new Error('toBlob')); }, 'image/png'); });
    });
  }

  if (shareDlg && shareDataEl) {
    var shareData = null, shareBlob = null, shareObjUrl = null;
    try { shareData = JSON.parse(shareDataEl.textContent); } catch (e) { shareData = null; }
    var sImg = $('.js-share-img', shareDlg), sLoading = $('.js-share-loading', shareDlg);
    var sCopy = $('.js-share-copy', shareDlg), sDownload = $('.js-share-download', shareDlg);
    var canCopyImage = !!(window.ClipboardItem && navigator.clipboard && navigator.clipboard.write && window.isSecureContext);
    function openShare() {
      if (!shareData || !shareDlg.showModal) return;
      if (!shareDlg.open) shareDlg.showModal();
      if (shareBlob) return;
      sLoading.hidden = false; sLoading.textContent = '正在生成…';
      renderShare(shareData).then(function (blob) {
        shareBlob = blob;
        shareObjUrl = URL.createObjectURL(blob);
        sImg.src = shareObjUrl;
        sLoading.hidden = true;
        sCopy.hidden = !canCopyImage;
      }, function () { sLoading.textContent = '生成失败，请换个浏览器重试'; });
    }
    $$('.js-share-card').forEach(function (b) { b.addEventListener('click', openShare); });
    sDownload.addEventListener('click', function () {
      if (!shareObjUrl) return;
      var a = doc.createElement('a');
      a.href = shareObjUrl; a.download = (shareData.file || 'ai-daily') + '.png';
      doc.body.appendChild(a); a.click(); doc.body.removeChild(a);
      toast('已下载分享图');
    });
    sCopy.addEventListener('click', function () {
      if (!shareBlob) return;
      navigator.clipboard.write([new window.ClipboardItem({ 'image/png': shareBlob })]).then(
        function () { toast('已复制图片，可直接粘贴到聊天窗口'); },
        function () { toast('复制失败，请改用下载'); });
    });
    shareDlg.addEventListener('click', function (ev) { if (ev.target === shareDlg) shareDlg.close(); });
  }

  var TEXT_INPUTS = ['text', 'search', 'email', 'url', 'tel', 'password', 'number'];
  function typingTarget(ev) {
    var el = ev.target, tag = (el.tagName || '').toLowerCase();
    if (tag === 'input') return TEXT_INPUTS.indexOf((el.type || 'text').toLowerCase()) !== -1;
    return tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }
  function anyDialogOpen() { return (help && help.open) || (palette && palette.open) || (shareDlg && shareDlg.open); }

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
    var state = { cat: 'all', onlyTry: false, onlyTop: false, onlyUnread: false, onlyFollow: false, tag: '' };

    var movers = function () { return items.concat($$('.group-title', feed)); };
    var setDensity = function (d, quiet) {
      if (!quiet && feed.getAttribute('data-density') !== d) { smooth(function () { setDensity(d, true); }, movers()); toast({ title: '只看标题', summary: '标题 + 摘要', full: '完整内容' }[d]); return; }
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
      state.onlyFollow = q.get('follow') === '1';
      state.tag = q.get('tag') || '';
    };
    var writeUrl = function () {
      var q = new URLSearchParams();
      if (state.cat !== 'all') q.set('cat', state.cat);
      if (state.onlyTry) q.set('try', '1');
      if (state.onlyTop) q.set('top', '1');
      if (state.onlyUnread) q.set('unread', '1');
      if (state.onlyFollow) q.set('follow', '1');
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
      var shown = 0, unread = 0, fl = follows(), hits = 0;
      if (!fl.length) state.onlyFollow = false;
      items.forEach(function (it) {
        var read = isRead(it.dataset.id);
        if (!read) unread++;
        var ok = (state.cat === 'all' || it.dataset.cat === state.cat) &&
          (!state.onlyTry || it.dataset.act === 'try') &&
          (!state.onlyTop || Number(it.dataset.imp) >= 4) &&
          (!state.onlyUnread || !read) &&
          (!state.onlyFollow || followHit(it, fl)) &&
          (!state.tag || (' ' + it.dataset.tags + ' ').indexOf(' ' + state.tag + ' ') !== -1);
        it.hidden = !ok;
        if (ok) shown++;
        if (followHit(it, fl)) hits++;
      });
      groups.forEach(function (g) {
        var n = $$('.item:not([hidden])', g).length;
        g.hidden = n === 0;
        var c = $('.group-title .count', g);
        if (c) c.textContent = n;
      });
      $$('.js-cats .cat-btn').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.cat === state.cat)); });
      var boxes = { '.js-only-try': state.onlyTry, '.js-only-top': state.onlyTop, '.js-only-unread': state.onlyUnread, '.js-only-follow': state.onlyFollow };
      var ff = $('.js-follow-filter'); if (ff) ff.hidden = fl.length === 0;
      var fc = $('.js-follow-count'); if (fc) fc.textContent = hits;
      var fn = $('.js-follow-note'); if (fn) { fn.hidden = !hits || state.onlyFollow; fn.textContent = '关注的标签本期有 ' + hits + ' 条'; }
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
    var applySmooth = function () { smooth(apply, movers()); };
    $$('.js-cats .cat-btn').forEach(function (b) { b.addEventListener('click', function () { state.cat = b.dataset.cat; applySmooth(); }); });
    [['.js-only-try', 'onlyTry'], ['.js-only-top', 'onlyTop'], ['.js-only-unread', 'onlyUnread'], ['.js-only-follow', 'onlyFollow']].forEach(function (p) {
      var b = $(p[0]); if (b) b.addEventListener('change', function () { state[p[1]] = b.checked; applySmooth(); });
    });
    doc.addEventListener('click', function (ev) {
      var t = ev.target.closest('.js-tag');
      if (t) { state.tag = state.tag === t.dataset.tag ? '' : t.dataset.tag; applySmooth(); return; }
      if (ev.target.closest('.js-clear-tag')) { state.tag = ''; applySmooth(); return; }
      if (ev.target.closest('.js-reset')) { state = { cat: 'all', onlyTry: false, onlyTop: false, onlyUnread: false, onlyFollow: false, tag: '' }; applySmooth(); }
    });
    window.addEventListener('storage', function (e) { if (e.key === READ_KEY) apply(); });
    readUrl();
    apply();
    followHooks.push(function () { apply(); });

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
        case 'o': if (focused) { var f = focused; smooth(function () { f.classList.toggle('is-expanded'); }, movers()); markRead(f.dataset.id); } break;
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
