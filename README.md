# BTC Desk — 비트코인 자동 갱신 대시보드

4시간마다 GitHub Actions가 데이터를 수집하고, 정적 HTML을 생성해 gh-pages로 배포합니다.
설계 원칙은 기존 주식 스크리너와 동일합니다. **수치 산출은 파이썬 결정론적 규칙, 해석은 사람.**

## 리포 구조

```
btc-desk/
├─ fetch_btc.py                # 수집 + 지표 계산 → data/latest.json
├─ build_page.py               # latest.json → public/index.html
├─ brief.py                    # 텔레그램 브리프 (선택)
├─ .github/workflows/btc.yml   # ← btc.yml 을 이 경로로 넣을 것
├─ data/
│   ├─ latest.json
│   └─ history/YYYY-MM-DD.json # 일자별 스냅샷 (백테스트용 축적)
└─ public/index.html
```

## 설치 순서

1. 새 리포지토리 생성 (예: `OCW-1027/BTC-DESK`). 기존 스크리너 리포와 분리해야
   Pages 배포 락 경합이 생기지 않습니다.
2. `fetch_btc.py`, `build_page.py`, `brief.py`, `README.md`를 루트에 업로드.
3. `btc.yml`을 **`.github/workflows/btc.yml`** 경로로 업로드.
   (브라우저 Monaco 에디터로 YAML을 직접 편집하면 자동 들여쓰기로 깨질 수 있으니
   로컬에서 준비한 파일을 업로드하는 방식을 권장)
4. Settings → Actions → General → Workflow permissions를
   **Read and write permissions**로 변경.
5. Actions 탭에서 `BTC Desk` → `Run workflow`로 1회 수동 실행.
   성공하면 `gh-pages` 브랜치가 생성됩니다.
6. Cloudflare Pages에서 이 리포를 연결하고 Production branch를 `gh-pages`,
   빌드 명령 없음(Static)으로 설정.

## 텔레그램 (선택)

Settings → Secrets and variables → Actions 에 추가:

| 이름 | 값 |
|---|---|
| `TG_TOKEN` | BotFather 발급 토큰 |
| `TG_CHAT` | 채팅 ID |

미설정이면 해당 스텝은 건너뜁니다.

## 데이터 소스

| 항목 | 1차 | 폴백 |
|---|---|---|
| 일봉 OHLCV | OKX `history-candles` | Coinbase Exchange |
| 현재가 | OKX ticker | CoinGecko simple/price |
| 펀딩비 (현재/이력) | OKX `funding-rate` | — |
| 미결제약정 | OKX `open-interest` + Rubik | — |
| 롱/숏 계정비율 | OKX Rubik | — |
| 테이커 매수/매도 | OKX Rubik | — |
| 공포탐욕지수 | Alternative.me | — |
| 선물 베이시스 | Deribit book summary | — |

전부 무인증·무료입니다. **Binance(HTTP 451)와 Bybit(403)은 GitHub Actions
러너 IP에서 차단되므로 사용하지 않습니다.** 개별 소스가 실패해도 해당 항목만
`null`이 되고 나머지는 정상 생성됩니다.

## 산출 지표

- **추세**: SMA 20/50/200, 20주 SMA, 21주 EMA, 50주 SMA
- **불마켓 서포트 밴드(BMSB)**: 20주 SMA와 21주 EMA로 구성되는 밴드
- **모멘텀**: RSI(14), MACD(12/26/9) 히스토그램
- **변동성**: ATR(14), 실현변동성 30일 연율
- **레벨**: 52주 고저 및 위치%, 90일 스윙 기준 피보나치 되돌림/확장
- **파생**: 펀딩비(현재·7일·30일 평균·연율·마이너스 비율), OI 및 7일 변화,
  롱/숏 계정비율, 테이커 매수/매도, Deribit 기간구조 프리미엄
- **심리**: 공포탐욕지수

## 시그널 채점

10개 항목을 각 −2 ~ +2로 채점해 합산합니다 (범위 ±20).

| 시그널 | +점수 조건 | −점수 조건 |
|---|---|---|
| BMSB | 밴드 상단 위 | 밴드 하향 이탈 |
| 50주 SMA | 상단 | 하단 |
| 200일 SMA | 상단 | 하단 |
| RSI(14) | ≤30 과매도 | ≥70 과열 |
| MACD-H | 양전 | 음전 |
| 펀딩비 7일 | 마이너스(숏 우위) | >0.03% 롱 과밀 |
| OI 7일 | 가격↑+OI↑ | 가격↓+OI↑ |
| 공포탐욕 | ≤25 극단적 공포 | ≥75 극단적 탐욕 |
| 52주 위치 | <15% | >85% |
| 롱/숏 비율 | <0.9 숏 편중 | >1.6 롱 편중 |

합계 +5 이상 강세 우위, −5 이하 약세 우위, 그 사이는 중립.
**펀딩비·공포탐욕·롱숏비율은 역발상 지표**로 채점됩니다.

## 갱신 주기

기본 4시간 (UTC 0/4/8/12/16/20시 18분). 분을 18로 둔 것은 정시 큐 혼잡을
피하기 위함입니다. 더 자주 필요하면 cron을 `18 */2 * * *` 등으로 조정하되,
`concurrency.cancel-in-progress: false`는 유지해야 배포가 겹치지 않습니다.

## 확장 아이디어

- `data/history/*.json` 축적 후 시그널 점수 대비 N일 수익률 백테스트
- ETF 순유입 (Farside 등 HTML 파싱 — 이용약관 확인 필요)
- FRED API로 DGS10/DGS30/CPI 추가 (무료 키 발급 필요)
- 청산 밀집 구간 추정 (Coinglass 유료 API)
- Gemini 무료 티어로 브리프 자동 해설 (수치는 반드시 JSON 값만 주입)

---

정보 제공 목적이며 투자 자문이 아닙니다. 파생상품은 원금 전액 손실이 가능합니다.

---

## 실시간 계층 (2단 구조)

페이지는 성격이 다른 두 층으로 나뉩니다. 이 분리가 핵심입니다.

| 층 | 내용 | 갱신 | 방식 |
|---|---|---|---|
| **실시간** | 현재가, 24h 변화율, 각 레벨까지의 거리, 저항/지지 재분류 | 초 단위 | 브라우저 → OKX WebSocket |
| **스냅샷** | SMA/BMSB/RSI/MACD/ATR, 펀딩비, OI, 롱숏, F&G, 시그널 점수 | 4시간 | GitHub Actions 빌드 |

이동평균이나 펀딩비 7일 평균은 초 단위로 바뀌지 않으므로 실시간일 필요가 없습니다.
반대로 현재가는 실시간이어야 하고, 이건 서버 빌드로는 불가능합니다.

### 동작

- `wss://ws.okx.com:8443/ws/v5/public` 의 `tickers` 채널을 구독합니다.
- WebSocket 실패 시 4회까지 지수 백오프로 재연결하고, 그래도 안 되면
  REST 5초 폴링으로 자동 전환합니다.
- 탭이 백그라운드로 가면 연결을 끊고, 돌아오면 재연결합니다 (배터리·쿼터 절약).
- 헤더의 점 색으로 상태를 표시합니다. 초록 점멸=실시간, 빨강=폴백, 회색=일시정지.

### CORS

OKX는 요청 Origin을 그대로 허용합니다 (`https://ocw-1027.github.io` 로 확인).
WebSocket은 CORS 자체가 적용되지 않으므로 더 안전한 1차 경로입니다.

### TradingView 임베드 위젯과의 관계

기존 대시보드에 쓰신 `embed-widget-ticker-tape` 등은 iframe 안에서 트레이딩뷰가
직접 시세를 그리는 방식이라 간단하고 확실합니다. 다만 **iframe 내부 값을
자바스크립트로 읽을 수 없어** 커스텀 지표나 레벨 거리 계산에는 쓸 수 없습니다.
그래서 시세 표시는 위젯, 계산이 필요한 부분은 WebSocket으로 나누는 편이 좋습니다.
두 방식은 함께 써도 충돌하지 않습니다.
