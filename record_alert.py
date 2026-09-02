#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TradingView 웹훅 이벤트를 일자별 파일에 append.

일자·시장별 파일 분리는 의도적이다. 단일 공유 로그 파일은 병렬 잡이
동시에 커밋할 때 머지 충돌을 일으킨다.
"""
import json, os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "data", "alerts")

ALLOWED = {"event", "symbol", "price", "tf", "note", "at"}


def main():
    raw = os.environ.get("TV_EVENT", "").strip()
    if not raw or raw in ("null", "{}"):
        print("이벤트 페이로드 없음 - 건너뜀")
        return
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"페이로드 파싱 실패: {e}")
        return
    if not isinstance(p, dict):
        print("페이로드가 객체가 아님 - 건너뜀")
        return

    # 화이트리스트 필드만 채택. 페이로드는 외부 입력이므로 신뢰하지 않는다.
    rec = {k: p[k] for k in ALLOWED if k in p}
    rec["recorded_at"] = datetime.now(JST).isoformat()
    for k in ("event", "symbol", "tf", "note"):
        if k in rec:
            rec[k] = str(rec[k])[:200]
    if "price" in rec:
        try:
            rec["price"] = float(rec["price"])
        except (TypeError, ValueError):
            rec["price"] = None

    os.makedirs(DIR, exist_ok=True)
    day = datetime.now(JST).strftime("%Y-%m-%d")
    path = os.path.join(DIR, f"{day}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"기록: {rec.get('event')} @ {rec.get('price')} -> {os.path.basename(path)}")


def recent(n=8):
    """build_page 에서 호출. 최근 알림 n건을 최신순으로 반환."""
    if not os.path.isdir(DIR):
        return []
    out = []
    for fn in sorted(os.listdir(DIR), reverse=True):
        if not fn.endswith(".jsonl"):
            continue
        try:
            with open(os.path.join(DIR, fn), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            continue
        if len(out) >= n * 3:
            break
    out.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
    return out[:n]


if __name__ == "__main__":
    main()
