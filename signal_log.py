#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Desk — 신호 로거 / 전진 검증(walk-forward)

백테스트는 과거 데이터에 맞춰 고른 결과지만, 오늘 이후 발생하는 신호는 조작할 수 없다.
이 스크립트는 매 실행 시:
  1) 각 타임프레임에서 지금 발생한 신호를 기록한다 (data/signals/<tf>.jsonl)
  2) 이미 기록된 신호 중 결과가 확정된 것을 채점한다
  3) 누적 실적을 data/forward.json 으로 출력한다

백테스트와 동일한 규칙·손절·익절을 사용하므로 직접 비교가 가능하다.
"""
import json, os, math, time
from datetime import datetime, timezone, timedelta

import backtest as BT   # 규칙·지표·비용 정의를 그대로 재사용

BASE = os.path.dirname(os.path.abspath(__file__))
SIG = os.path.join(BASE, "data", "signals")
OUT = os.path.join(BASE, "data")
JST = timezone(timedelta(hours=9))

HPB = {"15m": 0.25, "1H": 1, "4H": 4, "1D": 24}


def load_lines(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    return out


def save_lines(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def score_open(rows, d, hold):
    """미확정 신호를 현재 데이터로 채점. 확정되면 결과를 채운다."""
    tmap = {t: i for i, t in enumerate(d["t"])}
    changed = 0
    for r in rows:
        if r.get("done"):
            continue
        i = tmap.get(r["t"])
        if i is None or i + 1 >= d["n"]:
            continue
        side = r["side"]
        entry = r["entry"]
        sl, tp = r["sl"], r["tp"]
        end = min(d["n"] - 1, i + 1 + hold)
        exit_px, how, bars, mae = None, "open", 0, 0.0
        for j in range(i + 1, end + 1):
            bars = j - i
            adv = ((d["l"][j] / entry - 1) * 100 if side > 0
                   else (d["h"][j] / entry - 1) * -100)
            mae = min(mae, adv)
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
            if i + 1 + hold <= d["n"] - 1:
                exit_px, how = d["c"][end], "time"
            else:
                r["mae"] = round(mae, 3)
                r["bars_so_far"] = bars
                r["unrealized"] = round((d["c"][d["n"] - 1] / entry - 1) * 100 * side, 3)
                continue
        r["done"] = True
        r["exit"] = round(exit_px, 2)
        r["how"] = how
        r["bars"] = bars
        r["mae"] = round(mae, 3)
        r["ret"] = round((exit_px / entry - 1) * 100 * side, 3)
        changed += 1
    return changed


def run():
    os.makedirs(SIG, exist_ok=True)
    print("== 신호 로거 ==")
    summary = {}

    for bar, ko, need, per_day in BT.TFS:
        # 최신 데이터 (캐시 무시하고 최근분만 새로 수집)
        cands = BT.fetch(bar, min(need, 3000))
        if len(cands) < 300:
            continue
        d = BT.build(cands)
        hold = max(6, per_day * 3)
        path = os.path.join(SIG, f"{bar}.jsonl")
        rows = load_lines(path)
        known = set(str(r["t"]) + "|" + r["key"] for r in rows if "t" in r and "key" in r)

        # 최근 구간에서 신규 신호 탐지 (과거 소급 기록은 하지 않음)
        first_run = len(rows) == 0
        scan_from = max(210, d["n"] - (200 if first_run else 40))
        added = 0
        for i in range(scan_from, d["n"] - 1):
            atr = d["atr"][i]
            entry = d["o"][i + 1]
            if not atr or not entry:
                continue
            for key, side in BT.rules(d, i):
                if side == 0:
                    side = 1 if d["c"][i] > d["c"][i - 1] else -1
                uid = str(d["t"][i]) + "|" + key
                if uid in known:
                    continue
                known.add(uid)
                rows.append({
                    "t": d["t"][i], "key": key, "side": side,
                    "tf": bar,
                    "at": datetime.fromtimestamp(d["t"][i] / 1000, JST).strftime("%Y-%m-%d %H:%M"),
                    "signal_close": round(d["c"][i], 2),
                    "entry": round(entry, 2),
                    "atr": round(atr, 2),
                    "sl": round(entry - side * atr * 1.5, 2),
                    "tp": round(entry + side * atr * 3.0, 2),
                    "done": False,
                })
                added += 1

        rows.sort(key=lambda r: r["t"])
        # 오래된 확정분은 요약만 남기고 정리 (파일 비대 방지)
        if len(rows) > 4000:
            rows = rows[-4000:]
        ch = score_open(rows, d, hold)
        save_lines(path, rows)

        done = [r for r in rows if r.get("done")]
        openn = [r for r in rows if not r.get("done")]
        by_rule = {}
        for r in done:
            by_rule.setdefault(r["key"], []).append(r)

        stats_rows = []
        for key, trs in by_rule.items():
            st = BT.stats([{"ret": t["ret"], "mae": t.get("mae", 0),
                            "bars": t.get("bars", 0), "how": t.get("how", "time")}
                           for t in trs], HPB[bar])
            if not st:
                continue
            ko_n, jp_n, sd = BT.RULE_META.get(key, (key, key, 0))
            st.update({"key": key, "ko": ko_n, "jp": jp_n, "side": sd})
            stats_rows.append(st)
        stats_rows.sort(key=lambda x: -x["net"])

        summary[bar] = {
            "ko": ko, "total": len(rows), "done": len(done), "open": len(openn),
            "since": rows[0]["at"] if rows else None,
            "rules": stats_rows,
            "recent": [
                {k: r.get(k) for k in ("at", "key", "side", "entry", "sl", "tp",
                                       "done", "ret", "how", "unrealized")}
                for r in rows[-12:][::-1]
            ],
        }
        print(f"  {bar}: 신규 {added} | 확정 {len(done)} | 진행중 {len(openn)}"
              f" | 이번 채점 {ch}")

    payload = {
        "generated_at_jst": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "params": {"sl_atr": 1.5, "tp_atr": 3.0,
                   "fee_roundtrip": BT.FEE_ROUNDTRIP, "funding_per_8h": BT.FUND_PER_8H},
        "summary": summary,
    }
    with open(os.path.join(OUT, "forward.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("== 완료: data/forward.json ==")
    return payload


if __name__ == "__main__":
    run()
