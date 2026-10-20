/* Minimal QR Code encoder (byte mode, ECC level M, versions 1–10).
   Follows ISO/IEC 18004 as laid out in Project Nayuki's reference implementation (MIT).
   Used only to draw the link on share cards; returns a square boolean matrix. */
(function (root) {
  "use strict";
  var ECC_PER_BLOCK = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
  var NUM_BLOCKS = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
  var FORMAT_ECL_M = 0;

  function rawModules(ver) {
    var r = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
      var n = Math.floor(ver / 7) + 2;
      r -= (25 * n - 10) * n - 55;
      if (ver >= 7) r -= 36;
    }
    return r;
  }
  function dataCodewords(ver) {
    return Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver];
  }
  function gfMul(x, y) {
    var z = 0;
    for (var i = 7; i >= 0; i--) {
      z = (z << 1) ^ ((z >>> 7) * 0x11d);
      z ^= ((y >>> i) & 1) * x;
    }
    return z;
  }
  function rsDivisor(deg) {
    var res = [];
    for (var i = 0; i < deg - 1; i++) res.push(0);
    res.push(1);
    var r = 1;
    for (i = 0; i < deg; i++) {
      for (var j = 0; j < deg; j++) {
        res[j] = gfMul(res[j], r);
        if (j + 1 < deg) res[j] ^= res[j + 1];
      }
      r = gfMul(r, 0x02);
    }
    return res;
  }
  function rsRemainder(data, div) {
    var res = div.map(function () { return 0; });
    data.forEach(function (b) {
      var f = b ^ res.shift();
      res.push(0);
      div.forEach(function (c, i) { res[i] ^= gfMul(c, f); });
    });
    return res;
  }
  function bit(x, i) { return ((x >>> i) & 1) !== 0; }

  function encode(text, forceMask) {
    var bytes = Array.prototype.slice.call(new TextEncoder().encode(text));
    var ver, ccBits;
    for (ver = 1; ver <= 10; ver++) {
      ccBits = ver < 10 ? 8 : 16;
      if (4 + ccBits + bytes.length * 8 <= dataCodewords(ver) * 8) break;
    }
    if (ver > 10) throw new Error("text too long for QR");

    // --- data bit stream ---
    var bb = [];
    function put(val, len) { for (var i = len - 1; i >= 0; i--) bb.push((val >>> i) & 1); }
    put(4, 4);
    put(bytes.length, ccBits);
    bytes.forEach(function (b) { put(b, 8); });
    var cap = dataCodewords(ver) * 8;
    put(0, Math.min(4, cap - bb.length));
    put(0, (8 - bb.length % 8) % 8);
    for (var pad = 0xec; bb.length < cap; pad ^= 0xec ^ 0x11) put(pad, 8);
    var data = [];
    for (var i = 0; i < bb.length; i += 8) {
      var v = 0;
      for (var j = 0; j < 8; j++) v = (v << 1) | bb[i + j];
      data.push(v);
    }

    // --- error correction + interleave ---
    var nb = NUM_BLOCKS[ver], eccLen = ECC_PER_BLOCK[ver];
    var raw = Math.floor(rawModules(ver) / 8);
    var nShort = nb - raw % nb, shortLen = Math.floor(raw / nb);
    var div = rsDivisor(eccLen), blocks = [], k = 0;
    for (i = 0; i < nb; i++) {
      var dat = data.slice(k, k + shortLen - eccLen + (i < nShort ? 0 : 1));
      k += dat.length;
      var ecc = rsRemainder(dat, div);
      if (i < nShort) dat.push(0);
      blocks.push(dat.concat(ecc));
    }
    var words = [];
    for (i = 0; i < blocks[0].length; i++)
      for (j = 0; j < nb; j++)
        if (i !== shortLen - eccLen || j >= nShort) words.push(blocks[j][i]);

    // --- matrix ---
    var size = ver * 4 + 17, mod = [], fn = [];
    for (i = 0; i < size; i++) { mod.push(new Array(size).fill(false)); fn.push(new Array(size).fill(false)); }
    function setF(x, y, d) { mod[y][x] = d; fn[y][x] = true; }

    for (i = 0; i < size; i++) { setF(6, i, i % 2 === 0); setF(i, 6, i % 2 === 0); }
    [[3, 3], [size - 4, 3], [3, size - 4]].forEach(function (c) {
      for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
        var d = Math.max(Math.abs(dx), Math.abs(dy)), xx = c[0] + dx, yy = c[1] + dy;
        if (xx >= 0 && xx < size && yy >= 0 && yy < size) setF(xx, yy, d !== 2 && d !== 4);
      }
    });
    var align = [];
    if (ver > 1) {
      var na = Math.floor(ver / 7) + 2;
      var step = Math.ceil((ver * 4 + 4) / (na * 2 - 2)) * 2;
      align = [6];
      for (var pos = size - 7; align.length < na; pos -= step) align.splice(1, 0, pos);
    }
    var last = align.length - 1;
    align.forEach(function (ax, ai) {
      align.forEach(function (ay, aj) {
        if ((ai === 0 && aj === 0) || (ai === 0 && aj === last) || (ai === last && aj === 0)) return;
        for (var dy = -2; dy <= 2; dy++) for (var dx = -2; dx <= 2; dx++)
          setF(ax + dx, ay + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      });
    });
    function drawFormat(mask) {
      var d = (FORMAT_ECL_M << 3) | mask, rem = d;
      for (var t = 0; t < 10; t++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      var bits = ((d << 10) | rem) ^ 0x5412, q;
      for (q = 0; q <= 5; q++) setF(8, q, bit(bits, q));
      setF(8, 7, bit(bits, 6));
      setF(8, 8, bit(bits, 7));
      setF(7, 8, bit(bits, 8));
      for (q = 9; q < 15; q++) setF(14 - q, 8, bit(bits, q));
      for (q = 0; q < 8; q++) setF(size - 1 - q, 8, bit(bits, q));
      for (q = 8; q < 15; q++) setF(8, size - 15 + q, bit(bits, q));
      setF(8, size - 8, true);
    }
    drawFormat(0);
    if (ver >= 7) {
      var rem = ver;
      for (i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
      var vb = (ver << 12) | rem;
      for (i = 0; i < 18; i++) {
        var a = size - 11 + i % 3, b = Math.floor(i / 3);
        setF(a, b, bit(vb, i));
        setF(b, a, bit(vb, i));
      }
    }

    // codewords in zigzag order
    var n = 0;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) for (j = 0; j < 2; j++) {
        var x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
        if (!fn[y][x] && n < words.length * 8) { mod[y][x] = bit(words[n >>> 3], 7 - (n & 7)); n++; }
      }
    }

    var MASKS = [
      function (x, y) { return (x + y) % 2 === 0; },
      function (x, y) { return y % 2 === 0; },
      function (x) { return x % 3 === 0; },
      function (x, y) { return (x + y) % 3 === 0; },
      function (x, y) { return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; },
      function (x, y) { return x * y % 2 + x * y % 3 === 0; },
      function (x, y) { return (x * y % 2 + x * y % 3) % 2 === 0; },
      function (x, y) { return ((x + y) % 2 + x * y % 3) % 2 === 0; }
    ];
    function applyMask(m) {
      for (var y = 0; y < size; y++) for (var x = 0; x < size; x++)
        if (!fn[y][x] && MASKS[m](x, y)) mod[y][x] = !mod[y][x];
    }
    var PAT = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], PATR = PAT.slice().reverse();
    function lineScore(get) {
      var s = 0, run = 1, i, p;
      for (i = 1; i < size; i++) {
        if (get(i) === get(i - 1)) { run++; if (run === 5) s += 3; else if (run > 5) s++; }
        else run = 1;
      }
      for (i = -4; i + 11 <= size + 4; i++) {
        var f1 = true, f2 = true;
        for (p = 0; p < 11; p++) {
          var c = i + p, v = c >= 0 && c < size && get(c) ? 1 : 0;
          if (v !== PAT[p]) f1 = false;
          if (v !== PATR[p]) f2 = false;
        }
        if (f1) s += 40;
        if (f2) s += 40;
      }
      return s;
    }
    function penalty() {
      var s = 0, dark = 0, x, y;
      for (y = 0; y < size; y++) s += lineScore(function (i) { return mod[y][i]; });
      for (x = 0; x < size; x++) s += lineScore(function (i) { return mod[i][x]; });
      for (y = 0; y < size - 1; y++) for (x = 0; x < size - 1; x++) {
        var c = mod[y][x];
        if (c === mod[y][x + 1] && c === mod[y + 1][x] && c === mod[y + 1][x + 1]) s += 3;
      }
      for (y = 0; y < size; y++) for (x = 0; x < size; x++) if (mod[y][x]) dark++;
      var total = size * size;
      s += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
      return s;
    }
    var best = 0, bestScore = Infinity;
    for (var m = 0; m < 8; m++) {
      applyMask(m); drawFormat(m);
      var sc = penalty();
      if (sc < bestScore) { bestScore = sc; best = m; }
      applyMask(m);
    }
    if (forceMask >= 0 && forceMask < 8) best = forceMask;
    applyMask(best); drawFormat(best);
    return { size: size, version: ver, mask: best, get: function (x, y) { return mod[y][x]; } };
  }

  root.ADLqr = encode;
  if (typeof module !== "undefined" && module.exports) module.exports = encode;
})(typeof window !== "undefined" ? window : globalThis);
