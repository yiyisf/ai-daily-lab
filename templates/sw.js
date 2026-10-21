/* AI Daily Lab service worker — makes repeat visits instant and keeps the site readable on a flaky network.
   - versioned assets (?v=hash) and Google Fonts files: cache first (they never change under the same URL)
   - Google Fonts stylesheet: stale-while-revalidate
   - pages and data JSON: network first, fall back to the cached copy after 3.5 s or when offline
   Nothing is precached; the cache fills as pages are read and is trimmed to the most recent entries. */
'use strict';
var VERSION = 'adl-v1';
var PAGES = VERSION + '-pages', STATIC = VERSION + '-static';
var PAGE_LIMIT = 80, STATIC_LIMIT = 120, NETWORK_TIMEOUT = 3500;

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf(VERSION) !== 0; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trim(name, limit) {
  return caches.open(name).then(function (c) {
    return c.keys().then(function (keys) {
      return Promise.all(keys.slice(0, Math.max(0, keys.length - limit)).map(function (k) { return c.delete(k); }));
    });
  });
}
function put(name, req, res, limit) {
  if (!res || !(res.ok || res.type === 'opaque')) return;
  var copy = res.clone();
  caches.open(name).then(function (c) { return c.put(req, copy); }).then(function () { return trim(name, limit); });
}
function cacheFirst(req) {
  return caches.match(req).then(function (hit) {
    return hit || fetch(req).then(function (res) { put(STATIC, req, res, STATIC_LIMIT); return res; });
  });
}
function staleWhileRevalidate(req) {
  return caches.match(req).then(function (hit) {
    var net = fetch(req).then(function (res) { put(STATIC, req, res, STATIC_LIMIT); return res; });
    return hit || net;
  });
}
function networkFirst(req) {
  return new Promise(function (resolve, reject) {
    var settled = false;
    var fallback = function () {
      return caches.match(req, { ignoreSearch: req.mode === 'navigate' }).then(function (hit) {
        if (hit && !settled) { settled = true; resolve(hit); }
        return hit;
      });
    };
    var timer = setTimeout(fallback, NETWORK_TIMEOUT);
    fetch(req).then(function (res) {
      clearTimeout(timer);
      put(PAGES, req, res, PAGE_LIMIT);
      if (!settled) { settled = true; resolve(res); }
    }, function (err) {
      clearTimeout(timer);
      fallback().then(function (hit) { if (!hit && !settled) { settled = true; reject(err); } });
    });
  });
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.hostname === 'fonts.gstatic.com') { e.respondWith(cacheFirst(req)); return; }
  if (url.hostname === 'fonts.googleapis.com') { e.respondWith(staleWhileRevalidate(req)); return; }
  if (url.origin !== self.location.origin || url.pathname.indexOf(new URL(self.registration.scope).pathname) !== 0) return;
  if (/\/assets\//.test(url.pathname) && url.searchParams.has('v')) { e.respondWith(cacheFirst(req)); return; }
  if (req.mode === 'navigate' || /\.(html|json)$/.test(url.pathname) || url.pathname.slice(-1) === '/') { e.respondWith(networkFirst(req)); }
});
