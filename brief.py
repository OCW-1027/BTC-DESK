#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BTC Desk - 텔레그램 브리프 전송.
수치는 fetch_btc.py가 산출한 값만 사용한다 (모델 추정치 금지).
환경변수: TG_TOKEN, TG_CHAT (없으면 표준출력으로만 인쇄)
"""
import json, os, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PAGE_URL = os.environ.get("PAGE_URL", "")


def f(v, d=0, s="", plus=False):
    if v is None:
        return "—"
    t = f"{v:,.{d}f}"
    return ("+" if plus and v > 0 else "") + t + s


def load_prev():
    """직전 영업일 스냅샷. 밤사이 변화 비교용."""
    d = os.path.join(BASE, "data", "history")
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    for fn in reversed(files[:-1]):          # 오늘 파일 제외
        try:
            return json.load(open(os.path.join(d, fn), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def overnight(m, prev):
    """전 스냅샷 대비 변화. 없으면 빈 리스트."""
    if not prev:
        return []
    out = []
    a, b = m["price"]["last"], prev["price"]["last"]
    if a and b:
        out.append(f"  가격 {f(b,0)} → {f(a,0)}  ({f((a/b-1)*100,2,'%',True)})")
    sa, sb = m["signals"]["total"], prev["signals"]["total"]
    if sa != sb:
        out.append(f"  시그널 점수 {sb:+d} → {sa:+d}"
                   f"  ({prev['signals']['stance_ko']} → {m['signals']['stance_ko']})")
    # 스탠스가 바뀐 개별 시그널
    pm = {x["key"]: x for x in prev["signals"]["items"]}
    for x in m["signals"]["items"]:
        o = pm.get(x["key"])
        if o and o["score"] != x["score"]:
            out.append(f"  ⚑ {x['ko']}  ({o['score']:+d} → {x['score']:+d})")
    return out


def main():
    m = json.load(open(os.path.join(BASE, "data", "latest.json"), encoding="utf-8"))
    prev = load_prev()
    kind = os.environ.get("BRIEF_KIND", "adhoc")
    p, l, sg, fd = m["price"], m["levels"], m["signals"], m["funding"]
    px = p["last"]

    # 현재가 기준 최근접 저항 / 지지
    cands = [("52W High", l["high_52w"]), ("90D High", l["swing_high_90d"]),
             ("50W SMA", l.get("sma_50w")), ("200D SMA", m["ma"]["sma200"]),
             ("20D SMA", m["ma"]["sma20"]), ("BMSB上", l["bull_band_high"]),
             ("BMSB下", l["bull_band_low"]), ("Fib .618", l["fib"]["0.618"]),
             ("90D Low", l["swing_low_90d"])]
    res = sorted([c for c in cands if c[1] and c[1] > px], key=lambda x: x[1])[:2]
    sup = sorted([c for c in cands if c[1] and c[1] < px], key=lambda x: -x[1])[:2]

    pos = [s for s in sg["items"] if s["score"] > 0]
    neg = [s for s in sg["items"] if s["score"] < 0]

    head = "☀️ *BTC 아침 브리프*" if kind == "morning" else "₿ *BTC 데스크 브리프*"
    lines = [
        f"{head}  `{m['generated_at_jst']}`",
        "",
        f"*{f(px,0)} USD*   24h {f(p['chg_24h'],2,'%',True)} · "
        f"7d {f(p['chg_7d'],2,'%',True)} · 30d {f(p['chg_30d'],1,'%',True)}",
        f"종합 스탠스: *{sg['stance_ko']}*  ({sg['total']:+d} / ±{sg['max']})",
        "",
    ]
    ov = overnight(m, prev)
    if ov:
        lines += ["*전일 대비*"] + ov + [""]
    lines += [
        "*레벨*",
        "  저항  " + " / ".join(f"{n} {f(v,0)}" for n, v in res) if res else "  저항  —",
        "  지지  " + " / ".join(f"{n} {f(v,0)}" for n, v in sup) if sup else "  지지  —",
        "",
        "*파생*",
        f"  펀딩 {f(fd['current'],4,'%',True)} (7d {f(fd['avg_7d'],4,'%',True)})",
        f"  OI {f(m['oi']['current_btc'],0)} BTC ({f(m['oi']['chg_7d'],1,'%',True)} 7d)",
        f"  L/S {f(m['ls_ratio']['current'],2)} · F&G {m['fng']['current']} {m['fng']['label']}",
        f"  RSI {f(m['momentum']['rsi14'],1)} · ATR {f(m['momentum']['atr14'],0)} "
        f"· RV30 {f(m['momentum']['rv30'],1,'%')}",
        "",
    ]
    if pos:
        lines.append("*강세 요인*")
        lines += [f"  ＋{s['score']} {s['ko']} — {s['detail']}" for s in pos]
    if neg:
        lines.append("*약세 요인*")
        lines += [f"  {s['score']} {s['ko']} — {s['detail']}" for s in neg]

    if PAGE_URL:
        lines += ["", f"[대시보드]({PAGE_URL})"]
    lines += ["", "_수치는 자동 산출. 해석·매매 판단은 별도._"]

    text = "\n".join(lines)
    print(text)

    tok, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
    if not tok or not chat:
        print("\n[TG_TOKEN/TG_CHAT 미설정 - 전송 생략]")
        return
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        print("\n전송 완료:", r.status)


if __name__ == "__main__":
    main()
