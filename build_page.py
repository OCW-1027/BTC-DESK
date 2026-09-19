#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BTC Desk - latest.json -> index.html 렌더링 (한국어/일본어 전환)"""
import json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from record_alert import recent as recent_alerts

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data", "latest.json")
OUT = os.path.join(BASE, "public", "index.html")

T = {
    "title": {"ko": "BTC 데스크", "jp": "BTC デスク"},
    "stance": {"ko": "종합 스탠스", "jp": "総合スタンス"},
    "price": {"ko": "가격 · 추세", "jp": "価格・トレンド"},
    "levels": {"ko": "주요 레벨", "jp": "主要レベル"},
    "deriv": {"ko": "파생 · 수급", "jp": "デリバティブ・需給"},
    "signals": {"ko": "시그널", "jp": "シグナル"},
    "basis": {"ko": "선물 베이시스 (연율 환산)", "jp": "先物ベーシス（年率換算）"},
    "chart": {"ko": "최근 180일", "jp": "直近180日"},
    "updated": {"ko": "갱신", "jp": "更新"},
    "disc": {"ko": "정보 제공 목적이며 투자 자문이 아닙니다. 파생상품은 원금 전액 손실이 가능합니다.",
             "jp": "情報提供目的であり投資助言ではありません。デリバティブは元本全損の可能性があります。"},
}


def f(v, d=0, suffix="", plus=False):
    if v is None:
        return "—"
    s = f"{v:,.{d}f}"
    if plus and v > 0:
        s = "+" + s
    return s + suffix


def cls(v, inv=False):
    if v is None:
        return "n"
    if inv:
        v = -v
    return "u" if v > 0 else ("d" if v < 0 else "n")


def build():
    m = json.load(open(DATA, encoding="utf-8"))
    p, l, mo, sg = m["price"], m["levels"], m["momentum"], m["signals"]
    fd, oi, fng = m["funding"], m["oi"], m["fng"]
    px = p["last"]

    # 레벨 정렬 (현재가 기준 위/아래)
    lv = []
    for name_ko, name_jp, val in [
        ("52주 고점", "52週高値", l["high_52w"]),
        ("1.618 확장", "1.618拡張", l["fib"]["ext_1.618"]),
        ("90일 고점", "90日高値", l["swing_high_90d"]),
        ("50주 SMA", "50週SMA", l.get("sma_50w")),
        ("200일 SMA", "200日SMA", m["ma"]["sma200"]),
        ("50일 SMA", "50日SMA", m["ma"]["sma50"]),
        ("20일 SMA", "20日SMA", m["ma"]["sma20"]),
        ("BMSB 상단", "BMSB上限", l["bull_band_high"]),
        ("BMSB 하단", "BMSB下限", l["bull_band_low"]),
        ("피보 0.618", "フィボ0.618", l["fib"]["0.618"]),
        ("피보 0.786", "フィボ0.786", l["fib"]["0.786"]),
        ("90일 저점", "90日安値", l["swing_low_90d"]),
        ("52주 저점", "52週安値", l["low_52w"]),
    ]:
        if val:
            lv.append((name_ko, name_jp, val, (val / px - 1) * 100))
    lv.sort(key=lambda x: -x[2])

    lv_rows = ""
    marker_done = False
    for ko, jp, val, dist in lv:
        if not marker_done and val < px:
            lv_rows += ('<tr class="now" id="nowrow"><td colspan="3">▶ '
                        '<span data-ko="현재가" data-jp="現在値">현재가</span> '
                        f'<b id="nowpx">{f(px,0)}</b></td></tr>')
            marker_done = True
        side = "res" if val > px else "sup"
        lv_rows += (f'<tr class="{side}" data-lv="{val:.2f}">'
                    f'<td><span data-ko="{ko}" data-jp="{jp}">{ko}</span></td>'
                    f'<td class="num">{f(val,0)}</td>'
                    f'<td class="num dist {cls(dist)}">{f(dist,1,"%",True)}</td></tr>')
    if not marker_done:
        lv_rows += f'<tr class="now"><td colspan="3">▶ <b>{f(px,0)}</b></td></tr>'

    sig_rows = ""
    for s in sg["items"]:
        c = "u" if s["score"] > 0 else ("d" if s["score"] < 0 else "n")
        sig_rows += (f'<tr><td class="num {c}"><b>{s["score"]:+d}</b></td>'
                     f'<td><span data-ko="{s["ko"]}" data-jp="{s["jp"]}">{s["ko"]}</span></td>'
                     f'<td class="dim">{s["detail"]}</td></tr>')

    basis_rows = ""
    for c in (m.get("basis") or {}).get("curve", [])[-6:]:
        basis_rows += (f'<tr><td>{c["name"].replace("BTC-","")}</td>'
                       f'<td class="num">{f(c["mid"],0)}</td>'
                       f'<td class="num {cls(c["premium_pct"])}">'
                       f'{f(c["premium_pct"],2,"%",True)}</td></tr>')

    LB = {"break_up": ("저항 상향 돌파", "レジスタンス上抜け"),
          "break_down": ("지지 하향 이탈", "サポート下抜け"),
          "rsi_ob": ("RSI 과열권", "RSI 過熱圏"),
          "rsi_os": ("RSI 과매도권", "RSI 売られ過ぎ"),
          "bmsb_lost": ("BMSB 이탈", "BMSB 下抜け"),
          "bmsb_recl": ("BMSB 회복", "BMSB 回復"),
          "vol_spike": ("변동성 급증", "ボラティリティ急増")}
    al = recent_alerts(8)
    if al:
        rows = ""
        for a in al:
            ko, jp = LB.get(a.get("event", ""), (a.get("event", "—"),) * 2)
            rows += (f'<tr><td class="dim">{a.get("recorded_at","")[5:16].replace("T"," ")}</td>'
                     f'<td><span data-ko="{ko}" data-jp="{jp}">{ko}</span></td>'
                     f'<td class="num">{f(a.get("price"),0)}</td>'
                     f'<td class="dim">{a.get("tf","")}</td></tr>')
        alerts_card = ('<div class="card" style="grid-column:1/-1">'
                       '<h2 data-ko="최근 알림 (TradingView)" data-jp="直近アラート（TradingView）">'
                       f'최근 알림 (TradingView)</h2><table>{rows}</table></div>')
    else:
        alerts_card = ""

    px_json = json.dumps(px)
    levels_json = json.dumps({
        "bmsb_low": l["bull_band_low"], "bmsb_high": l["bull_band_high"],
        "sma_50w": l.get("sma_50w"), "sma200": m["ma"]["sma200"],
    })
    spark = json.dumps([[x["t"], x["c"]] for x in m["ohlc"]])
    fund_hist = json.dumps(fd.get("hist", []))

    stance_c = {"bull": "u", "bear": "d", "neutral": "n"}[sg["stance"]]

    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Desk</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font:14px/1.5 -apple-system,"Hiragino Kaku Gothic ProN","Noto Sans KR",sans-serif;padding:14px;max-width:1180px;margin:0 auto}}
h1{{font-size:17px;font-weight:700;letter-spacing:-.3px}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:8px}}
.meta{{color:#6e7681;font-size:11px}}
.lang .mtflink{{background:#161b22;border:1px solid #30363d;color:#ffb224;padding:4px 10px;
  font-size:11px;border-radius:5px;text-decoration:none;margin-right:6px}}
.lang .mtflink:hover{{border-color:#ffb224}}
.lang button{{background:#161b22;border:1px solid #30363d;color:#8b949e;padding:4px 10px;cursor:pointer;font-size:11px;border-radius:5px;margin-left:4px}}
.lang button.on{{background:#1f6feb;color:#fff;border-color:#1f6feb}}
.hero{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin:12px 0;display:flex;gap:24px;align-items:baseline;flex-wrap:wrap}}
.hero .px{{font-size:34px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-1px}}
.hero .chg{{font-size:15px;font-variant-numeric:tabular-nums}}
.badge{{margin-left:auto;padding:7px 14px;border-radius:7px;font-weight:700;font-size:13px}}
.badge.u{{background:#0f5132;color:#7ee2a8}} .badge.d{{background:#5c1a1a;color:#ff9d9d}} .badge.n{{background:#30363d;color:#c9d1d9}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;align-items:start}}
.chartcard{{grid-column:1/-1}}
.sigcard{{grid-column:span 2}}
@media(max-width:940px){{.sigcard{{grid-column:1/-1}}}}
.chead{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}}
.chead h2{{margin:0}}
.rng{{display:flex;gap:3px}}
.rng button{{background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:10.5px;
  padding:3px 9px;border-radius:5px;cursor:pointer}}
.rng button.on{{background:#1f6feb;color:#fff;border-color:#1f6feb}}
.clegend{{margin-left:auto;font-size:10.5px;color:#6e7681;display:flex;align-items:center;gap:7px}}
.clegend i{{width:9px;height:3px;border-radius:2px;display:inline-block;margin-right:3px}}
#chartbox{{width:100%}}
#chartbox svg{{width:100%;height:auto;display:block}}
@media(max-width:560px){{.clegend{{display:none}}}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:13px}}
.card h2{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:.6px;margin-bottom:9px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td{{padding:4px 3px;border-bottom:1px solid #21262d}}
tr:last-child td{{border-bottom:0}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.u{{color:#3fb950}} .d{{color:#f85149}} .n{{color:#8b949e}} .dim{{color:#6e7681;font-size:11px}}
tr.res td{{color:#ffa198}} tr.sup td{{color:#7ee2a8}}
tr.now td{{background:#1f6feb22;color:#79c0ff;font-size:12px;padding:6px 3px;text-align:center}}
.kv{{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #21262d;font-size:13px}}
.kv:last-child{{border-bottom:0}} .kv span:last-child{{font-variant-numeric:tabular-nums}}
#c2 svg{{width:100%;height:80px;display:block;margin-top:6px}}
.live{{font-size:10.5px;color:#6e7681;margin-top:3px;display:flex;align-items:center;gap:5px}}
.dot{{width:6px;height:6px;border-radius:50%;background:#6e7681;display:inline-block}}
.dot.on{{background:#3fb950;animation:pulse 2s infinite}}
.dot.err{{background:#f85149}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.flash-u{{animation:fu .6s}} .flash-d{{animation:fd .6s}}
@keyframes fu{{0%{{color:#3fb950}}100%{{color:inherit}}}}
@keyframes fd{{0%{{color:#f85149}}100%{{color:inherit}}}}
footer{{color:#484f58;font-size:10.5px;margin-top:16px;text-align:center;line-height:1.6}}
@media(max-width:520px){{body{{padding:9px}} .hero .px{{font-size:27px}} .badge{{margin-left:0}}}}
</style></head><body>

<header>
  <div><h1>₿ BTC Desk</h1>
  <div class="meta">{T['updated']['ko']} {m['generated_at_jst']} · OKX / Deribit / Alternative.me</div></div>
  <div class="lang"><a class="mtflink" href="mtf.html">멀티 TF ↗</a><button id="bko" class="on" onclick="setLang('ko')">한국어</button><button id="bjp" onclick="setLang('jp')">日本語</button></div>
</header>

<div class="hero">
  <div>
    <div class="px" id="px">${f(px,0)}</div>
    <div class="live" id="live"><span class="dot"></span><span id="livetxt">연결 중…</span></div>
    <div class="chg">
      <span id="c24" class="{cls(p['chg_24h'])}">24h {f(p['chg_24h'],2,'%',True)}</span> ·
      <span class="{cls(p['chg_7d'])}">7d {f(p['chg_7d'],2,'%',True)}</span> ·
      <span class="{cls(p['chg_30d'])}">30d {f(p['chg_30d'],1,'%',True)}</span> ·
      <span class="{cls(p['chg_ytd'])}">YTD {f(p['chg_ytd'],1,'%',True)}</span>
    </div>
  </div>
  <div class="badge {stance_c}">
    <span data-ko="{sg['stance_ko']}" data-jp="{sg['stance_jp']}">{sg['stance_ko']}</span>
    &nbsp;{sg['total']:+d} / ±{sg['max']}
  </div>
</div>

<div class="grid">

<div class="card chartcard">
  <div class="chead">
    <h2 data-ko="가격 추이" data-jp="価格推移">가격 추이</h2>
    <div class="rng">
      <button data-d="30" onclick="setRange(30)">30D</button>
      <button data-d="90" onclick="setRange(90)">90D</button>
      <button data-d="180" class="on" onclick="setRange(180)">180D</button>
    </div>
    <span class="clegend">
      <i style="background:#58a6ff"></i>가격
      <i style="background:rgba(45,212,191,.45)"></i>BMSB
      <i style="background:#f0883e"></i>50W
      <i style="background:#a371f7"></i>200D
    </span>
  </div>
  <div id="chartbox"></div>
</div>

<div class="card"><h2 data-ko="{T['levels']['ko']}" data-jp="{T['levels']['jp']}">{T['levels']['ko']}</h2>
  <table>{lv_rows}</table></div>

<div class="card"><h2 data-ko="{T['deriv']['ko']}" data-jp="{T['deriv']['jp']}">{T['deriv']['ko']}</h2>
  <div class="kv"><span data-ko="펀딩비 (현재)" data-jp="資金調達率（現在）">펀딩비 (현재)</span>
    <span class="{cls(fd['current'])}">{f(fd['current'],4,'%',True)}</span></div>
  <div class="kv"><span data-ko="펀딩비 7일 평균" data-jp="資金調達率 7日平均">펀딩비 7일 평균</span>
    <span class="{cls(fd['avg_7d'])}">{f(fd['avg_7d'],4,'%',True)} ({f(fd['avg_7d']*3*365 if fd['avg_7d'] else None,1,'%/yr',True)})</span></div>
  <div class="kv"><span data-ko="7일 중 마이너스 비율" data-jp="7日間マイナス比率">7일 중 마이너스 비율</span>
    <span>{f(fd['neg_ratio_7d'],0,'%')}</span></div>
  <div class="kv"><span data-ko="미결제약정" data-jp="建玉">미결제약정</span>
    <span>{f(oi['current_btc'],0,' BTC')}</span></div>
  <div class="kv"><span data-ko="OI 7일 변화" data-jp="OI 7日変化">OI 7일 변화</span>
    <span class="{cls(oi['chg_7d'])}">{f(oi['chg_7d'],1,'%',True)}</span></div>
  <div class="kv"><span data-ko="롱/숏 계정비율" data-jp="ロング/ショート比">롱/숏 계정비율</span>
    <span>{f(m['ls_ratio']['current'],2)}</span></div>
  <div class="kv"><span data-ko="테이커 매수/매도" data-jp="テイカー買/売">테이커 매수/매도</span>
    <span>{f(m['taker']['buy_sell_ratio'],3)}</span></div>
  <div class="kv"><span data-ko="공포탐욕지수" data-jp="恐怖強欲指数">공포탐욕지수</span>
    <span>{fng['current']} · {fng['label']}</span></div>
</div>

<div class="card"><h2 data-ko="모멘텀 · 변동성" data-jp="モメンタム・ボラティリティ">모멘텀 · 변동성</h2>
  <div class="kv"><span>RSI (14D)</span><span>{f(mo['rsi14'],1)}</span></div>
  <div class="kv"><span>MACD Hist</span><span class="{cls(mo['macd_hist'])}">{f(mo['macd_hist'],1,'',True)}</span></div>
  <div class="kv"><span>ATR (14D)</span><span>{f(mo['atr14'],0)} ({f(mo['atr14']/px*100 if mo['atr14'] else None,2,'%')})</span></div>
  <div class="kv"><span data-ko="실현변동성 30일 (연율)" data-jp="実現ボラ30日（年率）">실현변동성 30일 (연율)</span>
    <span>{f(mo['rv30'],1,'%')}</span></div>
  <div class="kv"><span data-ko="52주 위치" data-jp="52週レンジ位置">52주 위치</span>
    <span>{f(l['pos_52w'],0,'%')}</span></div>
  <div id="c2" style="margin-top:8px"></div>
</div>

<div class="card sigcard"><h2 data-ko="{T['signals']['ko']}" data-jp="{T['signals']['jp']}">{T['signals']['ko']}</h2>
  <table>{sig_rows}</table></div>

{alerts_card}

<div class="card"><h2 data-ko="{T['basis']['ko']}" data-jp="{T['basis']['jp']}">{T['basis']['ko']}</h2>
  <table>{basis_rows}</table></div>

</div>

<footer>
  <span data-ko="{T['disc']['ko']}" data-jp="{T['disc']['jp']}">{T['disc']['ko']}</span><br>
  Auto-generated · {m['generated_at_utc'][:19]}Z
</footer>

<script>
function setLang(L){{
  document.querySelectorAll('[data-ko]').forEach(function(e){{e.textContent=e.getAttribute('data-'+L)}});
  document.getElementById('bko').className = L=='ko'?'on':'';
  document.getElementById('bjp').className = L=='jp'?'on':'';
  document.documentElement.lang = L=='ko'?'ko':'ja';
  try{{localStorage.setItem('btcdesk_lang',L)}}catch(e){{}}
}}
try{{var sv=localStorage.getItem('btcdesk_lang'); if(sv)setLang(sv)}}catch(e){{}}

var S={spark};
var LV={levels_json};
var RANGE=180;

function setRange(d){{
  RANGE=d;
  var bs=document.querySelectorAll('.rng button');
  for(var i=0;i<bs.length;i++) bs[i].className = (+bs[i].getAttribute('data-d')===d)?'on':'';
  drawChart();
}}

function drawChart(){{
  var box=document.getElementById('chartbox');
  if(!box||!S.length) return;
  var data=S.slice(Math.max(0,S.length-RANGE));
  // 컨테이너 실제 폭으로 그려 텍스트 왜곡을 막는다
  var W=Math.max(320,Math.round(box.clientWidth||1000));
  var narrow=W<560;
  var H=narrow?200:270, PL=8, PR=narrow?48:62, PT=10, PB=20;
  var n=data.length;
  var lo=Infinity,hi=-Infinity,i,v;
  for(i=0;i<n;i++){{v=data[i][1]; if(v<lo)lo=v; if(v>hi)hi=v;}}
  // 레벨이 범위에 가까우면 포함
  [LV.bmsb_low,LV.bmsb_high,LV.sma_50w,LV.sma200].forEach(function(x){{
    if(x==null) return;
    if(x>lo*0.90&&x<hi*1.10){{ if(x<lo)lo=x; if(x>hi)hi=x; }}
  }});
  var m=(hi-lo)*0.07||1; lo-=m; hi+=m;
  var X=function(i){{return PL+(W-PL-PR)*(n>1?i/(n-1):0.5)}};
  var Y=function(v){{return PT+(H-PT-PB)*(1-(v-lo)/(hi-lo))}};
  var FS=narrow?9:11;
  var out='<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'">';

  // 가로 눈금
  for(i=0;i<=4;i++){{
    var gv=lo+(hi-lo)*i/4, gy=Y(gv);
    out+='<line x1="'+PL+'" y1="'+gy.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+gy.toFixed(1)+'" stroke="#21262d" stroke-width="1"/>';
    out+='<text x="'+(W-PR+6)+'" y="'+(gy+3.5).toFixed(1)+'" fill="#6e7681" font-size="'+FS+'">'+Math.round(gv).toLocaleString()+'</text>';
  }}

  // BMSB 밴드
  if(LV.bmsb_low!=null&&LV.bmsb_high!=null&&LV.bmsb_high>lo&&LV.bmsb_low<hi){{
    var y1=Y(Math.min(hi,LV.bmsb_high)),y2=Y(Math.max(lo,LV.bmsb_low));
    out+='<rect x="'+PL+'" y="'+y1.toFixed(1)+'" width="'+(W-PL-PR)+'" height="'+Math.max(0,y2-y1).toFixed(1)+'" fill="rgba(45,212,191,.13)"/>';
  }}

  // 레벨 라인
  function lvline(v,col,lbl){{
    if(v==null||v<lo||v>hi) return '';
    var y=Y(v);
    return '<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+y.toFixed(1)+
           '" stroke="'+col+'" stroke-width="1" stroke-dasharray="5 4" opacity=".75"/>'+
           '<text x="'+(PL+4)+'" y="'+(y-4).toFixed(1)+'" fill="'+col+'" font-size="'+(FS-0.5)+'">'+lbl+'</text>';
  }}
  out+=lvline(LV.sma_50w,'#f0883e','50W SMA');
  out+=lvline(LV.sma200,'#a371f7','200D SMA');

  // 가격 영역 + 라인
  var dl='';
  for(i=0;i<n;i++) dl+=(i?'L':'M')+X(i).toFixed(1)+','+Y(data[i][1]).toFixed(1);
  out+='<path d="'+dl+'L'+X(n-1).toFixed(1)+','+(H-PB)+'L'+X(0).toFixed(1)+','+(H-PB)+'Z" fill="rgba(88,166,255,.13)"/>';
  out+='<path d="'+dl+'" stroke="#58a6ff" stroke-width="1.8" fill="none" stroke-linejoin="round"/>';

  // 현재가 마커
  var lastV=data[n-1][1],ly=Y(lastV);
  out+='<circle cx="'+X(n-1).toFixed(1)+'" cy="'+ly.toFixed(1)+'" r="3" fill="#58a6ff"/>';
  out+='<rect x="'+(W-PR+2)+'" y="'+(ly-8).toFixed(1)+'" width="'+(PR-4)+'" height="16" rx="3" fill="#1f6feb"/>';
  out+='<text x="'+(W-PR+6)+'" y="'+(ly+3.5).toFixed(1)+'" fill="#fff" font-size="'+FS+'" font-weight="700">'+Math.round(lastV).toLocaleString()+'</text>';

  // 날짜 라벨
  [0,Math.floor(n/2),n-1].forEach(function(idx){{
    if(idx<0||idx>=n) return;
    var d=new Date(data[idx][0]);
    var lb=(d.getMonth()+1)+'/'+d.getDate();
    out+='<text x="'+X(idx).toFixed(1)+'" y="'+(H-5)+'" fill="#6e7681" font-size="'+FS+'" text-anchor="'+(idx===0?'start':(idx===n-1?'end':'middle'))+'">'+lb+'</text>';
  }});
  out+='</svg>';
  box.innerHTML=out;
}}
drawChart();
var _rt;
window.addEventListener('resize',function(){{clearTimeout(_rt);_rt=setTimeout(drawChart,180);}});

var F={fund_hist};
if(F.length){{
  var fb=document.getElementById('c2');
  if(fb){{
    var W2=300,H2=80,mx=0;
    for(var i=0;i<F.length;i++) mx=Math.max(mx,Math.abs(F[i]));
    mx=mx||1;
    var o='<svg viewBox="0 0 '+W2+' '+H2+'" preserveAspectRatio="none">';
    var zy=H2/2, bw=W2/F.length;
    o+='<line x1="0" y1="'+zy+'" x2="'+W2+'" y2="'+zy+'" stroke="#30363d" stroke-width="1"/>';
    for(i=0;i<F.length;i++){{
      var hgt=Math.abs(F[i])/mx*(H2/2-2);
      var y=F[i]>=0?zy-hgt:zy;
      o+='<rect x="'+(i*bw).toFixed(2)+'" y="'+y.toFixed(2)+'" width="'+Math.max(0.8,bw-0.6).toFixed(2)+'" height="'+hgt.toFixed(2)+'" fill="'+(F[i]>=0?'#3fb95099':'#f8514999')+'"/>';
    }}
    fb.outerHTML='<div id="c2">'+o+'</svg></div>';
  }}
}}

// ── 실시간 계층: OKX WebSocket (실패 시 REST 폴링으로 폴백)
// 정적 스냅샷의 레벨/지표는 유지하고, 가격과 레벨까지의 거리만 실시간 갱신한다.
(function(){{
  var base = {px_json};
  var elPx=document.getElementById('px'), elNow=document.getElementById('nowpx');
  var elC24=document.getElementById('c24'), elDot=document.querySelector('.dot'),
      elTxt=document.getElementById('livetxt');
  var last=base, ws=null, poll=null, tries=0;

  function fmt(n){{return n.toLocaleString('en-US',{{maximumFractionDigits:0}})}}
  function status(cls,txt){{ if(elDot)elDot.className='dot '+cls; if(elTxt)elTxt.textContent=txt; }}

  function render(px, open24){{
    if(!isFinite(px)||px<=0) return;
    var up = px>=last;
    last = px;
    if(elPx){{ elPx.textContent='$'+fmt(px);
      elPx.classList.remove('flash-u','flash-d');
      void elPx.offsetWidth;
      elPx.classList.add(up?'flash-u':'flash-d'); }}
    if(elNow) elNow.textContent=fmt(px);
    if(open24 && elC24){{
      var c=(px/open24-1)*100;
      elC24.textContent='24h '+(c>0?'+':'')+c.toFixed(2)+'%';
      elC24.className = c>0?'u':(c<0?'d':'n');
    }}
    // 레벨까지의 거리 재계산 + 현재가 행 위치 이동
    var rows=[].slice.call(document.querySelectorAll('tr[data-lv]'));
    rows.forEach(function(tr){{
      var v=parseFloat(tr.getAttribute('data-lv'));
      var d=(v/px-1)*100, td=tr.querySelector('.dist');
      if(td){{ td.textContent=(d>0?'+':'')+d.toFixed(1)+'%';
               td.className='num dist '+(d>0?'u':(d<0?'d':'n')); }}
      tr.className=(v>px?'res':'sup');
    }});
    var nr=document.getElementById('nowrow');
    if(nr){{
      var below=rows.filter(function(tr){{return parseFloat(tr.getAttribute('data-lv'))<px}})[0];
      if(below) below.parentNode.insertBefore(nr, below);
      else if(rows.length) rows[rows.length-1].parentNode.appendChild(nr);
    }}
  }}

  function startPoll(){{
    if(poll) return;
    status('on','REST 폴링 5초');
    poll=setInterval(function(){{
      fetch('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP')
        .then(function(r){{return r.json()}})
        .then(function(j){{ var d=j.data&&j.data[0];
          if(d) render(parseFloat(d.last), parseFloat(d.open24h)); }})
        .catch(function(){{ status('err','연결 실패 · 스냅샷 표시'); }});
    }},5000);
  }}

  function connect(){{
    try{{ ws=new WebSocket('wss://ws.okx.com:8443/ws/v5/public'); }}
    catch(e){{ startPoll(); return; }}
    ws.onopen=function(){{
      tries=0; status('on','실시간 연결됨');
      ws.send(JSON.stringify({{op:'subscribe',args:[{{channel:'tickers',instId:'BTC-USDT-SWAP'}}]}}));
    }};
    ws.onmessage=function(e){{
      try{{ var m=JSON.parse(e.data);
        if(m.data&&m.data[0]&&m.data[0].last)
          render(parseFloat(m.data[0].last), parseFloat(m.data[0].open24h));
      }}catch(_){{}}
    }};
    ws.onerror=function(){{ try{{ws.close()}}catch(_){{}} }};
    ws.onclose=function(){{
      if(poll) return;
      tries++;
      if(tries<=4){{ status('err','재연결 '+tries+'…'); setTimeout(connect, 1500*tries); }}
      else startPoll();
    }};
  }}

  document.addEventListener('visibilitychange',function(){{
    if(document.hidden){{
      if(ws){{try{{ws.close()}}catch(_){{}}ws=null}}
      if(poll){{clearInterval(poll);poll=null}}
      status('','일시정지');
    }} else if(!ws&&!poll){{ tries=0; connect(); }}
  }});

  connect();
}})();
</script>
</body></html>"""

    # 대시보드 임베드용 경량 JSON (전체 latest.json 은 무거움)
    slim = {
        "updated": m["generated_at_jst"],
        "price": px,
        "chg_24h": p["chg_24h"], "chg_7d": p["chg_7d"], "chg_30d": p["chg_30d"],
        "score": sg["total"], "score_max": sg["max"],
        "stance": sg["stance"], "stance_ko": sg["stance_ko"], "stance_jp": sg["stance_jp"],
        "rsi": mo["rsi14"], "funding_7d": fd["avg_7d"],
        "oi_chg_7d": oi["chg_7d"], "fng": fng["current"], "fng_label": fng["label"],
        "levels": {
            "resistance": [{"name": n, "value": v} for n, _, v, _ in lv if v > px][-2:],
            "support": [{"name": n, "value": v} for n, _, v, _ in lv if v < px][:2],
            "bmsb_low": l["bull_band_low"], "bmsb_high": l["bull_band_high"],
            "sma_50w": l.get("sma_50w"), "sma200": m["ma"]["sma200"],
        },
        "top_signals": [{"ko": x["ko"], "jp": x["jp"], "score": x["score"]}
                        for x in sorted(sg["items"], key=lambda z: -abs(z["score"]))[:3]],
    }
    # static/ 자산을 public/ 으로 복사 (mtf.html, indicators.js 등)
    import shutil
    pub = os.path.dirname(OUT)
    os.makedirs(pub, exist_ok=True)
    st = os.path.join(BASE, "static")
    if os.path.isdir(st):
        for fn in sorted(os.listdir(st)):
            src = os.path.join(st, fn)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(pub, fn))
                print(f"  static: {fn}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(os.path.join(os.path.dirname(OUT), "btc.json"), "w", encoding="utf-8") as jf:
        json.dump(slim, jf, ensure_ascii=False, indent=1)
    print("경량 JSON: public/btc.json")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"생성 완료: {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    build()
