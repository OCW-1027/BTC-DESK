#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Desk - 데이터 수집 및 지표 계산
설계 원칙: 후보/수치 산출은 전부 파이썬 결정론적 규칙. 해석은 사람 또는 LLM.
의존성: 표준 라이브러리만 사용 (GitHub Actions에서 pip install 불필요)
"""
import json, os, ssl, sys, time, math
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; btc-desk/1.0)"}
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ---------------------------------------------------------------- HTTP
def http_json(url, timeout=25, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def safe(fn, label, default=None):
    """개별 소스 실패가 전체를 죽이지 않도록"""
    try:
        v = fn()
        print(f"  [ok]   {label}")
        return v
    except Exception as e:
        print(f"  [fail] {label}: {type(e).__name__} {str(e)[:90]}")
        return default


# ---------------------------------------------------------------- 지표
def ema(vals, n):
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))


def ema_series(vals, n):
    if len(vals) < n:
        return []
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    out = [e]
    for v in vals[n:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig:
        return None, None, None
    ef, es = ema_series(closes, fast), ema_series(closes, slow)
    ef = ef[len(ef) - len(es):]
    line = [a - b for a, b in zip(ef, es)]
    sl = ema_series(line, sig)
    if not sl:
        return None, None, None
    return line[-1], sl[-1], line[-1] - sl[-1]


def atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def realized_vol(closes, n=30):
    if len(closes) < n + 1:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(365) * 100


def pct(a, b):
    return None if not b else (a / b - 1) * 100


# ---------------------------------------------------------------- 소스
def okx_daily(limit=500):
    """OKX 일봉. 반환 최신순 -> 오래된순으로 뒤집음"""
    rows = []
    after = ""
    while len(rows) < limit:
        url = ("https://www.okx.com/api/v5/market/history-candles"
               f"?instId=BTC-USDT-SWAP&bar=1D&limit=100{after}")
        d = http_json(url)["data"]
        if not d:
            break
        rows += d
        after = f"&after={d[-1][0]}"
        time.sleep(0.25)
    rows = sorted(rows, key=lambda r: int(r[0]))
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]),
             "l": float(r[3]), "c": float(r[4]), "v": float(r[7])} for r in rows]


def coinbase_daily(limit=500):
    """폴백: Coinbase 현물 일봉 (미국 IP 허용)"""
    end = datetime.now(timezone.utc)
    out = []
    for chunk in range(3):
        e = end - timedelta(days=290 * chunk)
        s = e - timedelta(days=290)
        url = ("https://api.exchange.coinbase.com/products/BTC-USD/candles"
               f"?granularity=86400&start={s.isoformat()}&end={e.isoformat()}")
        d = http_json(url)
        out += d
        time.sleep(0.4)
        if len(out) >= limit:
            break
    out = sorted(out, key=lambda r: r[0])
    return [{"t": r[0] * 1000, "o": float(r[3]), "h": float(r[2]),
             "l": float(r[1]), "c": float(r[4]), "v": float(r[5])} for r in out]


def get_daily():
    d = safe(lambda: okx_daily(), "일봉 OKX")
    if d and len(d) > 200:
        return d, "OKX"
    d = safe(lambda: coinbase_daily(), "일봉 Coinbase(폴백)")
    if d:
        return d, "Coinbase"
    raise RuntimeError("일봉 데이터 확보 실패")


def get_ticker():
    def okx():
        r = http_json("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP")["data"][0]
        return {"last": float(r["last"]), "high24": float(r["high24h"]),
                "low24": float(r["low24h"]), "src": "OKX"}

    def cg():
        r = http_json("https://api.coingecko.com/api/v3/simple/price"
                      "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true")["bitcoin"]
        return {"last": float(r["usd"]), "high24": None, "low24": None, "src": "CoinGecko"}

    return safe(okx, "현재가 OKX") or safe(cg, "현재가 CoinGecko(폴백)") or {}


def get_funding():
    def okx_now():
        r = http_json("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")["data"][0]
        return float(r["fundingRate"]) * 100, int(r["fundingTime"])

    def okx_hist():
        out, after = [], ""
        for _ in range(3):
            url = ("https://www.okx.com/api/v5/public/funding-rate-history"
                   f"?instId=BTC-USDT-SWAP&limit=100{after}")
            d = http_json(url)["data"]
            if not d:
                break
            out += d
            after = f"&after={d[-1]['fundingTime']}"
            time.sleep(0.25)
        return [float(x["fundingRate"]) * 100 for x in out]

    cur = safe(okx_now, "펀딩비 현재")
    hist = safe(okx_hist, "펀딩비 이력", [])
    res = {"current": None, "next_time": None, "avg_7d": None,
           "avg_30d": None, "apr": None, "neg_ratio_7d": None}
    if cur:
        res["current"], res["next_time"] = cur[0], cur[1]
        res["apr"] = cur[0] * 3 * 365
    if hist:
        h7, h30 = hist[:21], hist[:90]
        res["avg_7d"] = sum(h7) / len(h7)
        res["avg_30d"] = sum(h30) / len(h30)
        res["neg_ratio_7d"] = sum(1 for x in h7 if x < 0) / len(h7) * 100
        res["hist"] = hist[:90][::-1]
    return res


def get_oi():
    def okx():
        r = http_json("https://www.okx.com/api/v5/public/open-interest"
                      "?instType=SWAP&instId=BTC-USDT-SWAP")["data"][0]
        return float(r["oiCcy"])

    def okx_hist():
        d = http_json("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume"
                      "?ccy=BTC&period=1D")["data"]
        return [[int(x[0]), float(x[1])] for x in sorted(d, key=lambda z: int(z[0]))]

    cur = safe(okx, "미결제약정 현재")
    hist = safe(okx_hist, "미결제약정 이력", [])
    res = {"current_btc": cur, "chg_7d": None, "hist": hist[-60:]}
    if hist and len(hist) > 7:
        res["chg_7d"] = pct(hist[-1][1], hist[-8][1])
    return res


def get_ls_ratio():
    def okx():
        d = http_json("https://www.okx.com/api/v5/rubik/stat/contracts/"
                      "long-short-account-ratio?ccy=BTC&period=1D")["data"]
        d = sorted(d, key=lambda z: int(z[0]))
        return [[int(x[0]), float(x[1])] for x in d]
    h = safe(okx, "롱숏 계정비율", [])
    return {"current": h[-1][1] if h else None, "hist": h[-60:]}


def get_taker():
    def okx():
        d = http_json("https://www.okx.com/api/v5/rubik/stat/taker-volume"
                      "?ccy=BTC&instType=SPOT&period=1D")["data"]
        d = sorted(d, key=lambda z: int(z[0]))
        return [[int(x[0]), float(x[1]), float(x[2])] for x in d]
    h = safe(okx, "테이커 매수/매도", [])
    cur = None
    if h:
        sell, buy = h[-1][1], h[-1][2]
        cur = buy / sell if sell else None
    return {"buy_sell_ratio": cur, "hist": h[-30:]}


def get_fng():
    def f():
        d = http_json("https://api.alternative.me/fng/?limit=60")["data"]
        return [{"t": int(x["timestamp"]), "v": int(x["value"]),
                 "c": x["value_classification"]} for x in d][::-1]
    h = safe(f, "공포탐욕지수", [])
    return {"current": h[-1]["v"] if h else None,
            "label": h[-1]["c"] if h else None,
            "avg_7d": sum(x["v"] for x in h[-7:]) / 7 if len(h) >= 7 else None,
            "hist": h}


def get_basis():
    """Deribit 선물 term structure -> 베이시스(연율)"""
    def f():
        r = http_json("https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
                      "?currency=BTC&kind=future")["result"]
        perp = next((x for x in r if x["instrument_name"] == "BTC-PERPETUAL"), None)
        futs = [x for x in r if x["instrument_name"] != "BTC-PERPETUAL" and x.get("mid_price")]
        if not perp or not futs:
            return None
        spot = perp.get("estimated_delivery_price") or perp.get("mid_price")
        out = []
        for x in futs:
            name = x["instrument_name"]
            out.append({"name": name, "mid": x["mid_price"],
                        "premium_pct": (x["mid_price"] / spot - 1) * 100})
        out.sort(key=lambda z: z["premium_pct"])
        return {"spot_ref": spot, "curve": out}
    return safe(f, "선물 베이시스(Deribit)", {})


# ---------------------------------------------------------------- 시그널
def build_signals(m):
    """결정론적 규칙. 각 시그널 -2 ~ +2 점수."""
    s = []
    px = m["price"]["last"]

    def add(key, ko, jp, score, detail):
        s.append({"key": key, "ko": ko, "jp": jp, "score": score, "detail": detail})

    # 1. 불마켓 서포트 밴드
    b_lo, b_hi = m["levels"]["bull_band_low"], m["levels"]["bull_band_high"]
    if b_lo and b_hi:
        if px > b_hi:
            add("bmsb", "불마켓 서포트 밴드 상단", "強気相場サポートバンド上",
                2, f"{px:,.0f} > {b_hi:,.0f} (20W SMA/21W EMA 위)")
        elif px > b_lo:
            add("bmsb", "밴드 내부 (경계)", "バンド内部（警戒）", 0,
                f"{b_lo:,.0f} ~ {b_hi:,.0f} 사이")
        else:
            add("bmsb", "밴드 하향 이탈", "バンド下抜け", -2,
                f"{px:,.0f} < {b_lo:,.0f} 사이클 구조 훼손")

    # 1b. 50주 SMA (사이클 바닥 판정선)
    w50 = m["levels"].get("sma_50w")
    if w50:
        add("w50", "50주선 상단 (사이클 바닥 시그널 유효)" if px > w50 else "50주선 하단",
            "50週線上" if px > w50 else "50週線下",
            2 if px > w50 else -2, f"50W SMA {w50:,.0f} 대비 {pct(px, w50):+.1f}%")

    # 2. 200일선
    m200 = m["ma"]["sma200"]
    if m200:
        add("ma200", "200일선 상단" if px > m200 else "200일선 하단",
            "200日線上" if px > m200 else "200日線下",
            1 if px > m200 else -1, f"200D {m200:,.0f} 대비 {pct(px, m200):+.1f}%")

    # 3. RSI
    r = m["momentum"]["rsi14"]
    if r:
        if r >= 70:
            add("rsi", "RSI 과열", "RSI 過熱", -1, f"RSI {r:.1f}")
        elif r <= 30:
            add("rsi", "RSI 과매도", "RSI 売られ過ぎ", 1, f"RSI {r:.1f}")
        else:
            add("rsi", "RSI 중립", "RSI 中立", 0, f"RSI {r:.1f}")

    # 4. MACD 히스토그램
    h = m["momentum"]["macd_hist"]
    if h is not None:
        add("macd", "MACD-H 양전" if h > 0 else "MACD-H 음전",
            "MACD-H プラス" if h > 0 else "MACD-H マイナス",
            1 if h > 0 else -1, f"Hist {h:+,.1f}")

    # 5. 펀딩비 (역발상)
    f = m["funding"]["avg_7d"]
    if f is not None:
        if f < 0:
            add("funding", "펀딩 마이너스 (숏 우위 = 숏스퀴즈 연료)",
                "資金調達率マイナス（ショート優勢）", 1, f"7일 평균 {f:+.4f}%")
        elif f > 0.03:
            add("funding", "펀딩 과열 (롱 과밀)", "資金調達率 過熱（ロング過密）",
                -2, f"7일 평균 {f:+.4f}% (연 {f*3*365:.0f}%)")
        else:
            add("funding", "펀딩 정상", "資金調達率 正常", 0, f"7일 평균 {f:+.4f}%")

    # 6. 미결제약정 변화
    oi = m["oi"]["chg_7d"]
    if oi is not None:
        chg7 = m["price"]["chg_7d"]
        if chg7 is not None:
            if chg7 > 0 and oi > 5:
                add("oi", "가격↑ + OI↑ (신규 자금 유입)", "価格↑ + OI↑（新規資金）",
                    1, f"OI 7일 {oi:+.1f}%")
            elif chg7 < 0 and oi > 5:
                add("oi", "가격↓ + OI↑ (숏 증가, 청산 위험)",
                    "価格↓ + OI↑（ショート増）", -1, f"OI 7일 {oi:+.1f}%")
            elif oi < -5:
                add("oi", "OI 감소 (레버리지 해소)", "OI 減少（レバ解消）",
                    0, f"OI 7일 {oi:+.1f}%")
            else:
                add("oi", "OI 안정", "OI 安定", 0, f"OI 7일 {oi:+.1f}%")

    # 7. 공포탐욕
    fg = m["fng"]["current"]
    if fg is not None:
        if fg >= 75:
            add("fng", "극단적 탐욕 (역발상 매도)", "極度の強欲", -2, f"F&G {fg}")
        elif fg <= 25:
            add("fng", "극단적 공포 (역발상 매수)", "極度の恐怖", 2, f"F&G {fg}")
        else:
            add("fng", "심리 중립", "センチメント中立", 0, f"F&G {fg}")

    # 8. 52주 위치
    p52 = m["levels"]["pos_52w"]
    if p52 is not None:
        if p52 > 85:
            add("pos52", "52주 고점권", "52週高値圏", -1, f"위치 {p52:.0f}%")
        elif p52 < 15:
            add("pos52", "52주 저점권", "52週安値圏", 1, f"위치 {p52:.0f}%")
        else:
            add("pos52", "52주 중간권", "52週レンジ中位", 0, f"위치 {p52:.0f}%")

    # 9. 롱숏 비율
    ls = m["ls_ratio"]["current"]
    if ls:
        if ls > 1.6:
            add("ls", "롱 편중 (역발상 주의)", "ロング偏重", -1, f"L/S {ls:.2f}")
        elif ls < 0.9:
            add("ls", "숏 편중 (스퀴즈 가능)", "ショート偏重", 1, f"L/S {ls:.2f}")
        else:
            add("ls", "포지션 균형", "ポジション均衡", 0, f"L/S {ls:.2f}")

    total = sum(x["score"] for x in s)
    mx = len(s) * 2
    if total >= 5:
        stance, sko, sjp = "bull", "강세 우위", "強気優勢"
    elif total <= -5:
        stance, sko, sjp = "bear", "약세 우위", "弱気優勢"
    else:
        stance, sko, sjp = "neutral", "중립 / 관망", "中立・様子見"
    return {"items": s, "total": total, "max": mx,
            "stance": stance, "stance_ko": sko, "stance_jp": sjp}


# ---------------------------------------------------------------- 메인
def main():
    print("== BTC Desk 수집 시작 ==")
    daily, dsrc = get_daily()
    closes = [d["c"] for d in daily]
    highs = [d["h"] for d in daily]
    lows = [d["l"] for d in daily]
    px_now = get_ticker()

    last = px_now.get("last") or closes[-1]

    # 주봉 집계 (최신 기준 역방향으로 7일씩 묶어 정렬 오차 방지)
    weekly = []
    for i in range(len(daily), 0, -7):
        chunk = daily[max(0, i - 7):i]
        if len(chunk) == 7:
            weekly.append(chunk[-1]["c"])
    weekly = weekly[::-1]

    # 불마켓 서포트 밴드 = 20주 SMA + 21주 EMA (표준 정의)
    w20s, w21e = sma(weekly, 20), ema(weekly, 21)
    bb_lo = bb_hi = None
    if w20s and w21e:
        bb_lo, bb_hi = min(w20s, w21e), max(w20s, w21e)
    w50s = sma(weekly, 50)

    hi52 = max(highs[-365:]) if len(highs) >= 365 else max(highs)
    lo52 = min(lows[-365:]) if len(lows) >= 365 else min(lows)
    hi90, lo90 = max(highs[-90:]), min(lows[-90:])
    rng = hi90 - lo90

    ml, ms, mh = macd(closes)

    m = {
        "generated_at_jst": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"ohlc": dsrc, "price": px_now.get("src")},
        "price": {
            "last": last,
            "chg_24h": pct(last, closes[-2]) if len(closes) > 1 else None,
            "chg_7d": pct(last, closes[-8]) if len(closes) > 8 else None,
            "chg_30d": pct(last, closes[-31]) if len(closes) > 31 else None,
            "chg_ytd": None,
            "high24": px_now.get("high24"), "low24": px_now.get("low24"),
        },
        "ma": {
            "sma20": sma(closes, 20), "sma50": sma(closes, 50),
            "sma200": sma(closes, 200), "ema21": ema(closes, 21),
        },
        "momentum": {
            "rsi14": rsi(closes), "macd": ml, "macd_signal": ms, "macd_hist": mh,
            "atr14": atr(highs, lows, closes),
            "rv30": realized_vol(closes, 30),
        },
        "levels": {
            "bull_band_low": bb_lo, "bull_band_high": bb_hi,
            "sma_50w": w50s, "sma_20w": w20s, "ema_21w": w21e,
            "high_52w": hi52, "low_52w": lo52,
            "pos_52w": (last - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else None,
            "swing_high_90d": hi90, "swing_low_90d": lo90,
            "fib": {
                "0.236": hi90 - rng * 0.236, "0.382": hi90 - rng * 0.382,
                "0.5": hi90 - rng * 0.5, "0.618": hi90 - rng * 0.618,
                "0.786": hi90 - rng * 0.786,
                "ext_1.618": hi90 + rng * 0.618,
            },
        },
        "funding": get_funding(),
        "oi": get_oi(),
        "ls_ratio": get_ls_ratio(),
        "taker": get_taker(),
        "fng": get_fng(),
        "basis": get_basis(),
        "ohlc": [{"t": d["t"], "c": d["c"]} for d in daily[-180:]],
    }

    # YTD
    yr = datetime.now(timezone.utc).year
    for d in daily:
        if datetime.fromtimestamp(d["t"] / 1000, timezone.utc).year == yr:
            m["price"]["chg_ytd"] = pct(last, d["o"])
            break

    m["signals"] = build_signals(m)

    os.makedirs(os.path.join(OUT_DIR, "history"), exist_ok=True)
    with open(os.path.join(OUT_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    day = datetime.now(JST).strftime("%Y-%m-%d")
    with open(os.path.join(OUT_DIR, "history", f"{day}.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)

    print(f"== 완료: {last:,.1f} USD / 점수 {m['signals']['total']:+d} "
          f"({m['signals']['stance_ko']}) ==")
    return m


if __name__ == "__main__":
    main()
