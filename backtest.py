#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Desk — 규칙 백테스트 엔진

타임프레임별로 지표 규칙이 과거에 실제로 통했는지 검증한다.
모든 지표는 증분(streaming) 계산이며, 각 시점에서 그 시점까지의 데이터만 사용한다.
(미래참조 없음. 신호는 봉 종가 확정 시점에 발생, 진입은 다음 봉 시가로 간주)

출력: data/backtest.json
"""
import json, os, time, math, urllib.request
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data")
CACHE = os.path.join(OUT, "candles")
JST = timezone(timedelta(hours=9))

# 타임프레임별 수집 목표 (봉 수)
TFS = [
    ("15m", "15분", 35000, 96),    # 약 1년, 하루 96봉
    ("1H",  "1시간", 20000, 24),   # 약 2.3년
    ("4H",  "4시간", 10000, 6),    # 약 4.5년
    ("1D",  "일봉",   2000, 1),    # 약 5.5년
]


def http_json(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(1.0 + i)
    raise last


def fetch(bar, need):
    """OKX 과거 봉 수집. 캐시가 있으면 재사용."""
    os.makedirs(CACHE, exist_ok=True)
    cf = os.path.join(CACHE, f"{bar}.json")
    if os.path.exists(cf):
        try:
            d = json.load(open(cf, encoding="utf-8"))
            if len(d) >= need * 0.9:
                print(f"  {bar}: 캐시 {len(d)}봉")
                return d
        except Exception:
            pass

    rows, after = [], ""
    while len(rows) < need:
        url = ("https://www.okx.com/api/v5/market/history-candles"
               f"?instId=BTC-USDT-SWAP&bar={bar}&limit=100{after}")
        d = http_json(url)["data"]
        if not d:
            break
        rows += d
        after = "&after=" + d[-1][0]
        time.sleep(0.1)
    rows = sorted(rows, key=lambda r: int(r[0]))
    out = [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]
    json.dump(out, open(cf, "w"), separators=(",", ":"))
    print(f"  {bar}: 수집 {len(out)}봉")
    return out


# ──────────────────────────────────────────── 증분 지표
def ema_stream(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def sma_stream(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    s = sum(vals[:n])
    out[n - 1] = s / n
    for i in range(n, len(vals)):
        s += vals[i] - vals[i - n]
        out[i] = s / n
    return out


def rsi_stream(c, n=14):
    out = [None] * len(c)
    if len(c) < n + 1:
        return out
    g = [0.0] * len(c)
    l = [0.0] * len(c)
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g[i] = d if d > 0 else 0.0
        l[i] = -d if d < 0 else 0.0
    ag = sum(g[1:n + 1]) / n
    al = sum(l[1:n + 1]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(c)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd_stream(c, f=12, s=26, sig=9):
    ef, es = ema_stream(c, f), ema_stream(c, s)
    line = [None] * len(c)
    for i in range(len(c)):
        if ef[i] is not None and es[i] is not None:
            line[i] = ef[i] - es[i]
    idx = [i for i, v in enumerate(line) if v is not None]
    hist = [None] * len(c)
    if len(idx) >= sig:
        vals = [line[i] for i in idx]
        sg = ema_stream(vals, sig)
        for j, i in enumerate(idx):
            if sg[j] is not None:
                hist[i] = line[i] - sg[j]
    return line, hist


def atr_stream(h, l, c, n=14):
    out = [None] * len(c)
    if len(c) < n + 1:
        return out
    tr = [0.0] * len(c)
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def boll_stream(c, n=20, k=2):
    mid = sma_stream(c, n)
    up, lo, pb, bw = [None] * len(c), [None] * len(c), [None] * len(c), [None] * len(c)
    s = s2 = 0.0
    for i in range(len(c)):
        s += c[i]; s2 += c[i] * c[i]
        if i >= n:
            s -= c[i - n]; s2 -= c[i - n] * c[i - n]
        if i >= n - 1:
            m = s / n
            var = max(0.0, s2 / n - m * m)
            sd = math.sqrt(var)
            up[i], lo[i] = m + k * sd, m - k * sd
            if up[i] > lo[i]:
                pb[i] = (c[i] - lo[i]) / (up[i] - lo[i])
            bw[i] = (up[i] - lo[i]) / m * 100 if m else None
    return mid, up, lo, pb, bw


def rolling_mid(h, l, n):
    """(최고+최저)/2 롤링. 일목용."""
    out = [None] * len(h)
    for i in range(n - 1, len(h)):
        hi = max(h[i - n + 1:i + 1])
        lo = min(l[i - n + 1:i + 1])
        out[i] = (hi + lo) / 2
    return out


def ichimoku_stream(h, l, c):
    ten = rolling_mid(h, l, 9)
    kij = rolling_mid(h, l, 26)
    b52 = rolling_mid(h, l, 52)
    n = len(c)
    cl, ch = [None] * n, [None] * n   # 현재 봉에 드리워진 구름 (26봉 전 값)
    for i in range(n):
        j = i - 26
        if j >= 0 and ten[j] is not None and kij[j] is not None and b52[j] is not None:
            a = (ten[j] + kij[j]) / 2
            b = b52[j]
            cl[i], ch[i] = min(a, b), max(a, b)
    return ten, kij, cl, ch


# ──────────────────────────────────────────── 지표 일괄
def build(cands):
    t = [r[0] for r in cands]
    o = [r[1] for r in cands]
    h = [r[2] for r in cands]
    l = [r[3] for r in cands]
    c = [r[4] for r in cands]
    d = {"t": t, "o": o, "h": h, "l": l, "c": c, "n": len(c)}
    for p in (5, 10, 20, 50, 60, 99, 125, 200):
        d[f"sma{p}"] = sma_stream(c, p)
    d["rsi"] = rsi_stream(c)
    d["macd"], d["hist"] = macd_stream(c)
    d["atr"] = atr_stream(h, l, c)
    d["bm"], d["bu"], d["bl"], d["pb"], d["bw"] = boll_stream(c)
    d["ten"], d["kij"], d["cl"], d["ch"] = ichimoku_stream(h, l, c)
    return d


# ──────────────────────────────────────────── 규칙 정의
def _x(prev, cur):
    """상향 교차 판정 헬퍼"""
    return prev is not None and cur is not None


def rules(d, i):
    """i번째 봉 종가 확정 시점의 신호. (키, 방향) 리스트 반환."""
    out = []
    c, p = d["c"], i - 1
    if p < 1:
        return out

    def v(k, j=None):
        return d[k][i if j is None else j]

    # 1. 일목 구름 상향 돌파
    if _x(v("ch", p), v("ch")) and c[p] <= v("ch", p) and c[i] > v("ch"):
        out.append(("ichi_break_up", 1))
    if _x(v("cl", p), v("cl")) and c[p] >= v("cl", p) and c[i] < v("cl"):
        out.append(("ichi_break_dn", -1))

    # 2. 전환선/기준선 교차
    if _x(v("ten", p), v("ten")) and _x(v("kij", p), v("kij")):
        if v("ten", p) <= v("kij", p) and v("ten") > v("kij"):
            out.append(("tk_cross_up", 1))
        if v("ten", p) >= v("kij", p) and v("ten") < v("kij"):
            out.append(("tk_cross_dn", -1))

    # 3. MACD 히스토그램 전환
    if _x(v("hist", p), v("hist")):
        if v("hist", p) <= 0 < v("hist"):
            out.append(("macd_flip_up", 1))
        if v("hist", p) >= 0 > v("hist"):
            out.append(("macd_flip_dn", -1))

    # 4. RSI 과매도 탈출 / 과열 이탈
    if _x(v("rsi", p), v("rsi")):
        if v("rsi", p) < 30 <= v("rsi"):
            out.append(("rsi_os_exit", 1))
        if v("rsi", p) > 70 >= v("rsi"):
            out.append(("rsi_ob_exit", -1))

    # 5. 볼린저 하단 이탈 후 복귀 / 상단 이탈 후 복귀
    if _x(v("pb", p), v("pb")):
        if v("pb", p) < 0 <= v("pb"):
            out.append(("bb_lower_recl", 1))
        if v("pb", p) > 1 >= v("pb"):
            out.append(("bb_upper_rej", -1))

    # 6. 스퀴즈 이후 확장 (밴드폭이 직전 50봉 최저였다가 확대)
    if i >= 60 and v("bw") is not None:
        w = [x for x in d["bw"][i - 50:i] if x is not None]
        if w and v("bw", p) is not None and v("bw", p) <= min(w) * 1.05 and v("bw") > v("bw", p):
            out.append(("squeeze_up", 1 if c[i] > c[p] else -1))

    # 7. SMA200 돌파
    if _x(v("sma200", p), v("sma200")):
        if c[p] <= v("sma200", p) and c[i] > v("sma200"):
            out.append(("sma200_up", 1))
        if c[p] >= v("sma200", p) and c[i] < v("sma200"):
            out.append(("sma200_dn", -1))

    # 8. 골든/데드 크로스 (50/200)
    if _x(v("sma50", p), v("sma50")) and _x(v("sma200", p), v("sma200")):
        if v("sma50", p) <= v("sma200", p) and v("sma50") > v("sma200"):
            out.append(("golden_cross", 1))
        if v("sma50", p) >= v("sma200", p) and v("sma50") < v("sma200"):
            out.append(("death_cross", -1))

    # 9. 복합: 구름 위 + MACD 양전 + RSI 50~70
    if (v("ch") is not None and c[i] > v("ch") and v("hist") is not None and v("hist") > 0
            and v("rsi") is not None and 50 <= v("rsi") < 70):
        if not (v("hist", p) is not None and v("hist", p) > 0
                and v("ch", p) is not None and c[p] > v("ch", p)
                and v("rsi", p) is not None and 50 <= v("rsi", p) < 70):
            out.append(("combo_bull", 1))

    # 10. 복합 약세
    if (v("cl") is not None and c[i] < v("cl") and v("hist") is not None and v("hist") < 0
            and v("rsi") is not None and 30 < v("rsi") <= 50):
        if not (v("hist", p) is not None and v("hist", p) < 0
                and v("cl", p) is not None and c[p] < v("cl", p)
                and v("rsi", p) is not None and 30 < v("rsi", p) <= 50):
            out.append(("combo_bear", -1))

    return out


RULE_META = {
    "ichi_break_up":  ("일목 구름 상향 돌파", "一目 雲 上抜け", 1),
    "ichi_break_dn":  ("일목 구름 하향 이탈", "一目 雲 下抜け", -1),
    "tk_cross_up":    ("전환선 기준선 상향 교차", "転換線 基準線 上抜け", 1),
    "tk_cross_dn":    ("전환선 기준선 하향 교차", "転換線 基準線 下抜け", -1),
    "macd_flip_up":   ("MACD 히스토그램 양전", "MACD ヒスト プラス転換", 1),
    "macd_flip_dn":   ("MACD 히스토그램 음전", "MACD ヒスト マイナス転換", -1),
    "rsi_os_exit":    ("RSI 과매도 탈출 (30 상향)", "RSI 売られ過ぎ脱出", 1),
    "rsi_ob_exit":    ("RSI 과열 이탈 (70 하향)", "RSI 過熱圏離脱", -1),
    "bb_lower_recl":  ("볼린저 하단 이탈 후 복귀", "BB下限 逸脱後 回復", 1),
    "bb_upper_rej":   ("볼린저 상단 이탈 후 복귀", "BB上限 逸脱後 回帰", -1),
    "squeeze_up":     ("스퀴즈 후 확장", "スクイーズ後 拡大", 0),
    "sma200_up":      ("SMA200 상향 돌파", "SMA200 上抜け", 1),
    "sma200_dn":      ("SMA200 하향 이탈", "SMA200 下抜け", -1),
    "golden_cross":   ("골든크로스 (50/200)", "ゴールデンクロス", 1),
    "death_cross":    ("데드크로스 (50/200)", "デッドクロス", -1),
    "combo_bull":     ("복합 강세 (구름위+MACD+RSI)", "複合 強気", 1),
    "combo_bear":     ("복합 약세 (구름아래+MACD+RSI)", "複合 弱気", -1),
}


# ──────────────────────────────────────────── 평가
def evaluate(d, hold_bars, sl_atr=1.5, tp_atr=3.0):
    """각 규칙별 성과 산출.
    진입: 신호 봉의 다음 봉 시가
    청산: ATR 손절/익절 우선, 미도달 시 hold_bars 후 종가
    """
    n = d["n"]
    res = {}
    for i in range(210, n - 1):
        sigs = rules(d, i)
        if not sigs:
            continue
        atr = d["atr"][i]
        if not atr or atr <= 0:
            continue
        entry = d["o"][i + 1]
        if not entry:
            continue
        for key, side in sigs:
            if side == 0:
                side = 1 if d["c"][i] > d["c"][i - 1] else -1
            sl = entry - side * atr * sl_atr
            tp = entry + side * atr * tp_atr
            exit_px, bars, how = None, 0, "time"
            end = min(n - 1, i + 1 + hold_bars)
            for j in range(i + 1, end + 1):
                bars = j - i
                if side > 0:
                    if d["l"][j] <= sl:
                        exit_px, how = sl, "sl"; break
                    if d["h"][j] >= tp:
                        exit_px, how = tp, "tp"; break
                else:
                    if d["h"][j] >= sl:
                        exit_px, how = sl, "sl"; break
                    if d["l"][j] <= tp:
                        exit_px, how = tp, "tp"; break
            if exit_px is None:
                exit_px = d["c"][end]
            ret = (exit_px / entry - 1) * 100 * side
            # 최대 역행폭
            mae = 0.0
            for j in range(i + 1, min(end, i + bars) + 1):
                adv = (d["l"][j] / entry - 1) * 100 if side > 0 else (d["h"][j] / entry - 1) * -100
                mae = min(mae, adv)
            r = res.setdefault(key, {"n": 0, "wins": 0, "rets": [], "maes": [],
                                     "sl": 0, "tp": 0, "time": 0, "bars": []})
            r["n"] += 1
            r["rets"].append(ret)
            r["maes"].append(mae)
            r["bars"].append(bars)
            r[how] += 1
            if ret > 0:
                r["wins"] += 1
    return res


# 왕복 수수료(테이커 0.05% × 2) + 펀딩 개략치
FEE_ROUNDTRIP = 0.10   # %
FUND_PER_8H = 0.01     # %


def summarize(res, tf_key, tf_ko, hold_bars, hours_per_bar):
    out = []
    for key, r in res.items():
        rets = r["rets"]
        if len(rets) < 8:      # 표본 부족은 제외
            continue
        wins = [x for x in rets if x > 0]
        loss = [x for x in rets if x <= 0]
        avg = sum(rets) / len(rets)
        srt = sorted(rets)
        med = srt[len(srt) // 2]
        aw = sum(wins) / len(wins) if wins else 0
        al = sum(loss) / len(loss) if loss else 0
        wr = len(wins) / len(rets) * 100
        pf = (sum(wins) / abs(sum(loss))) if loss and sum(loss) != 0 else None
        sd = math.sqrt(sum((x - avg) ** 2 for x in rets) / len(rets)) if len(rets) > 1 else 0
        # 누적 곡선 최대 낙폭
        cum, peak, mdd = 0.0, 0.0, 0.0
        for x in rets:
            cum += x
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        ko, jp, side = RULE_META.get(key, (key, key, 0))
        avg_bars = sum(r["bars"]) / len(r["bars"])
        fund_cost = FUND_PER_8H * (avg_bars * hours_per_bar / 8.0)
        cost = FEE_ROUNDTRIP + fund_cost
        net = avg - cost
        # 기대값이 0과 구분되는가 (t통계량)
        tstat = (avg / (sd / math.sqrt(len(rets)))) if sd > 0 else 0.0
        tstat_net = (net / (sd / math.sqrt(len(rets)))) if sd > 0 else 0.0
        out.append({
            "cost": cost, "net": net, "tstat": tstat, "tstat_net": tstat_net,
            "verdict": ("강" if (net > 0 and tstat_net > 2 and len(rets) >= 30) else
                        ("약" if (net > 0 and tstat_net > 1) else "무")),
            "key": key, "ko": ko, "jp": jp, "side": side,
            "tf": tf_key, "tf_ko": tf_ko,
            "n": len(rets), "winrate": wr, "avg": avg, "median": med,
            "avg_win": aw, "avg_loss": al,
            "pf": pf, "expectancy": avg, "stdev": sd,
            "mdd": mdd,
            "avg_mae": sum(r["maes"]) / len(r["maes"]),
            "exit_sl": r["sl"], "exit_tp": r["tp"], "exit_time": r["time"],
            "avg_bars": sum(r["bars"]) / len(r["bars"]),
            "hold": hold_bars,
        })
    out.sort(key=lambda x: -x["net"])
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    print("== 백테스트 시작 ==")
    all_res, meta = {}, {}
    for bar, ko, need, per_day in TFS:
        cands = fetch(bar, need)
        if len(cands) < 300:
            print(f"  {bar}: 데이터 부족, 건너뜀")
            continue
        d = build(cands)
        hold = max(6, per_day * 3)     # 약 3일 보유 상당
        t0 = time.time()
        res = evaluate(d, hold)
        hpb = {"15m": 0.25, "1H": 1, "4H": 4, "1D": 24}[bar]
        rows = summarize(res, bar, ko, hold, hpb)
        all_res[bar] = rows
        meta[bar] = {
            "ko": ko, "bars": len(cands), "hold": hold,
            "from": datetime.fromtimestamp(cands[0][0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
            "to": datetime.fromtimestamp(cands[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        }
        print(f"  {bar}: 규칙 {len(rows)}개 평가 ({time.time()-t0:.1f}초)")

    payload = {
        "generated_at_jst": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "params": {"sl_atr": 1.5, "tp_atr": 3.0, "entry": "next_bar_open",
                   "fee_roundtrip": FEE_ROUNDTRIP, "funding_per_8h": FUND_PER_8H},
        "meta": meta, "results": all_res,
    }
    with open(os.path.join(OUT, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"== 완료: data/backtest.json ==")
    return payload


if __name__ == "__main__":
    main()
