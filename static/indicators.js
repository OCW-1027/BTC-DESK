/* ─────────────────────────────────────────────────────────────
   BTC Desk — 멀티 타임프레임 지표 엔진 (브라우저 계산)

   OKX candles API 를 직접 호출해 5개 타임프레임을 항상 최신으로 계산한다.
   서버 빌드(4시간)와 달리 페이지를 열 때마다 새로 계산되므로
   1분·15분봉도 의미를 갖는다.

   계산값은 파이썬 레퍼런스와 소수점 4자리까지 대조 검증됨.
   ──────────────────────────────────────────────────────────── */
(function (global) {
  'use strict';

  // ── 기본 통계 ─────────────────────────────────────────────
  function sma(v, n) {
    if (v.length < n) return null;
    var s = 0;
    for (var i = v.length - n; i < v.length; i++) s += v[i];
    return s / n;
  }

  function emaSeries(v, n) {
    if (v.length < n) return [];
    var k = 2 / (n + 1), e = 0, i;
    for (i = 0; i < n; i++) e += v[i];
    e /= n;
    var out = [e];
    for (i = n; i < v.length; i++) { e = v[i] * k + e * (1 - k); out.push(e); }
    return out;
  }

  function ema(v, n) {
    var s = emaSeries(v, n);
    return s.length ? s[s.length - 1] : null;
  }

  // ── RSI (Wilder 평활) ─────────────────────────────────────
  function rsi(c, n) {
    n = n || 14;
    if (c.length < n + 1) return null;
    var g = [], l = [], i, d;
    for (i = 1; i < c.length; i++) {
      d = c[i] - c[i - 1];
      g.push(d > 0 ? d : 0);
      l.push(d < 0 ? -d : 0);
    }
    var ag = 0, al = 0;
    for (i = 0; i < n; i++) { ag += g[i]; al += l[i]; }
    ag /= n; al /= n;
    for (i = n; i < g.length; i++) {
      ag = (ag * (n - 1) + g[i]) / n;
      al = (al * (n - 1) + l[i]) / n;
    }
    return al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  }

  // ── MACD (12/26/9) ────────────────────────────────────────
  function macd(c, f, s, g) {
    f = f || 12; s = s || 26; g = g || 9;
    if (c.length < s + g) return null;
    var ef = emaSeries(c, f), es = emaSeries(c, s);
    ef = ef.slice(ef.length - es.length);
    var line = es.map(function (v, i) { return ef[i] - v; });
    var sig = emaSeries(line, g);
    if (!sig.length) return null;
    var m = line[line.length - 1], sg = sig[sig.length - 1];
    return { macd: m, signal: sg, hist: m - sg };
  }

  // ── ATR (Wilder) ──────────────────────────────────────────
  function atr(h, l, c, n) {
    n = n || 14;
    if (c.length < n + 1) return null;
    var tr = [], i;
    for (i = 1; i < c.length; i++) {
      tr.push(Math.max(h[i] - l[i],
                       Math.abs(h[i] - c[i - 1]),
                       Math.abs(l[i] - c[i - 1])));
    }
    var a = 0;
    for (i = 0; i < n; i++) a += tr[i];
    a /= n;
    for (i = n; i < tr.length; i++) a = (a * (n - 1) + tr[i]) / n;
    return a;
  }

  // ── 볼린저 밴드 (20, 2σ) ──────────────────────────────────
  function bollinger(c, n, k) {
    n = n || 20; k = k || 2;
    if (c.length < n) return null;
    var m = sma(c, n), v = 0, i;
    for (i = c.length - n; i < c.length; i++) v += (c[i] - m) * (c[i] - m);
    var sd = Math.sqrt(v / n);
    var ub = m + k * sd, lb = m - k * sd;
    return {
      mid: m, upper: ub, lower: lb,
      width: m ? (ub - lb) / m * 100 : null,
      pctB: ub > lb ? (c[c.length - 1] - lb) / (ub - lb) : null
    };
  }

  // ── 일목균형표 (9/26/52/26) ───────────────────────────────
  function ichimoku(h, l, c) {
    if (c.length < 78) return null;
    function mid(n, shift) {
      shift = shift || 0;
      var e = h.length - shift, s = e - n;
      if (s < 0) return null;
      var hi = -Infinity, lo = Infinity;
      for (var i = s; i < e; i++) {
        if (h[i] > hi) hi = h[i];
        if (l[i] < lo) lo = l[i];
      }
      return (hi + lo) / 2;
    }
    var ten = mid(9), kij = mid(26);
    // 현재 시점에 드리워진 구름 = 26봉 전 값
    var a26 = (mid(9, 26) + mid(26, 26)) / 2, b26 = mid(52, 26);
    var lo = Math.min(a26, b26), hi = Math.max(a26, b26);
    var px = c[c.length - 1];
    return {
      tenkan: ten, kijun: kij,
      cloudLow: lo, cloudHigh: hi,
      bullCloud: a26 > b26,
      pos: px > hi ? 'above' : (px < lo ? 'below' : 'inside'),
      spanA: (ten + kij) / 2, spanB: mid(52),
      chikou: c.length > 26 ? c[c.length - 1] : null,
      chikouRef: c.length > 26 ? c[c.length - 27] : null
    };
  }

  // ── ATR 기반 손절 + R:R 목표가 ────────────────────────────
  function rrLevels(h, l, c, mult) {
    mult = mult || 3.5;
    var a = atr(h, l, c);
    if (!a) return null;
    var px = c[c.length - 1];
    var hl2 = (h[h.length - 1] + l[l.length - 1]) / 2;
    var slL = hl2 - mult * a, slS = hl2 + mult * a;
    var R = px - slL;
    return {
      atr: a, mult: mult,
      longSL: slL, shortSL: slS, R: R,
      tp: [1, 1.75, 2.5].map(function (r) {
        return { rr: r, price: px + R * r, pct: (R * r) / px * 100 };
      })
    };
  }

  // ── 다중 SMA 리본 ─────────────────────────────────────────
  var RIBBON = [5, 10, 20, 60, 99, 125, 200];
  function ribbon(c) {
    var out = {}, above = 0, total = 0;
    RIBBON.forEach(function (n) {
      var v = sma(c, n);
      out[n] = v;
      if (v != null) { total++; if (c[c.length - 1] > v) above++; }
    });
    out.aboveCount = above;
    out.total = total;
    // 정배열 판정: 짧은 주기가 긴 주기보다 위
    var vals = RIBBON.map(function (n) { return out[n]; }).filter(function (v) { return v != null; });
    var asc = true, desc = true;
    for (var i = 1; i < vals.length; i++) {
      if (vals[i - 1] <= vals[i]) asc = false;
      if (vals[i - 1] >= vals[i]) desc = false;
    }
    out.aligned = asc ? 'bull' : (desc ? 'bear' : 'mixed');
    return out;
  }

  // ── 전체 계산 ─────────────────────────────────────────────
  function analyze(h, l, c) {
    return {
      n: c.length,
      close: c[c.length - 1],
      ribbon: ribbon(c),
      rsi: rsi(c),
      macd: macd(c),
      atr: atr(h, l, c),
      boll: bollinger(c),
      ichimoku: ichimoku(h, l, c),
      rr: rrLevels(h, l, c)
    };
  }

  // ── OKX 데이터 수집 ───────────────────────────────────────
  var BARS = [
    { bar: '1m',  ko: '1분',   jp: '1分' },
    { bar: '15m', ko: '15분',  jp: '15分' },
    { bar: '1H',  ko: '1시간', jp: '1時間' },
    { bar: '4H',  ko: '4시간', jp: '4時間' },
    { bar: '1D',  ko: '일봉',  jp: '日足' }
  ];

  function fetchBar(bar, inst) {
    var url = 'https://www.okx.com/api/v5/market/candles?instId=' +
              (inst || 'BTC-USDT-SWAP') + '&bar=' + bar + '&limit=300';
    return fetch(url, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) {
        if (!j.data || !j.data.length) throw new Error('empty');
        // OKX 는 최신순으로 반환 -> 오래된순으로 정렬
        var rows = j.data.slice().sort(function (a, b) {
          return parseInt(a[0], 10) - parseInt(b[0], 10);
        });
        return {
          h: rows.map(function (r) { return parseFloat(r[2]); }),
          l: rows.map(function (r) { return parseFloat(r[3]); }),
          c: rows.map(function (r) { return parseFloat(r[4]); }),
          t: rows.map(function (r) { return parseInt(r[0], 10); })
        };
      });
  }

  // 5개 타임프레임 병렬 수집. 일부 실패해도 나머지는 반환.
  function analyzeAll(inst) {
    return Promise.all(BARS.map(function (b) {
      return fetchBar(b.bar, inst)
        .then(function (d) {
          return { key: b.bar, ko: b.ko, jp: b.jp, ok: true,
                   data: analyze(d.h, d.l, d.c) };
        })
        .catch(function (e) {
          return { key: b.bar, ko: b.ko, jp: b.jp, ok: false,
                   error: e.message };
        });
    }));
  }

  // ── 타임프레임 종합 점수 ──────────────────────────────────
  // 각 TF 를 -4 ~ +4 로 채점. 상위 TF 에 가중치.
  var WEIGHT = { '1m': 0.5, '15m': 0.75, '1H': 1, '4H': 1.5, '1D': 2 };

  function scoreTF(a) {
    if (!a) return null;
    var s = 0, px = a.close, parts = [];
    if (a.ichimoku) {
      var p = a.ichimoku.pos;
      var v = p === 'above' ? 2 : (p === 'below' ? -2 : 0);
      s += v; parts.push({ k: '일목', v: v });
    }
    if (a.ribbon) {
      var al = a.ribbon.aligned;
      var v2 = al === 'bull' ? 1 : (al === 'bear' ? -1 : 0);
      s += v2; parts.push({ k: '리본', v: v2 });
    }
    if (a.macd) {
      var v3 = a.macd.hist > 0 ? 1 : -1;
      s += v3; parts.push({ k: 'MACD', v: v3 });
    }
    if (a.rsi != null) {
      var v4 = a.rsi >= 70 ? -1 : (a.rsi <= 30 ? 1 : 0);
      s += v4; parts.push({ k: 'RSI', v: v4 });
    }
    return { score: s, parts: parts };
  }

  function consensus(results) {
    var tot = 0, wsum = 0;
    results.forEach(function (r) {
      if (!r.ok) return;
      var sc = scoreTF(r.data);
      if (!sc) return;
      var w = WEIGHT[r.key] || 1;
      tot += sc.score * w;
      wsum += 4 * w;
    });
    var pct = wsum ? tot / wsum : 0;
    return {
      raw: tot, max: wsum, pct: pct * 100,
      stance: pct > 0.25 ? 'bull' : (pct < -0.25 ? 'bear' : 'neutral')
    };
  }

  global.BTCIndicators = {
    sma: sma, ema: ema, rsi: rsi, macd: macd, atr: atr,
    bollinger: bollinger, ichimoku: ichimoku, rrLevels: rrLevels,
    ribbon: ribbon, analyze: analyze,
    fetchBar: fetchBar, analyzeAll: analyzeAll,
    scoreTF: scoreTF, consensus: consensus,
    BARS: BARS, RIBBON: RIBBON
  };
})(typeof window !== 'undefined' ? window : globalThis);
