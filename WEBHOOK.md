# TradingView 웹훅 → BTC Desk 실시간 연동

## 왜 중계 레이어가 필요한가

TradingView 웹훅은 **커스텀 헤더를 보낼 수 없습니다.** GitHub의 `repository_dispatch`
API는 `Authorization` 헤더에 토큰을 요구하므로, TradingView가 GitHub를 직접 호출할
방법이 없습니다. 따라서 Cloudflare Worker가 중간에서 인증을 대행합니다.

시크릿은 헤더 대신 **JSON 본문**에 담아 검증합니다.

```
TradingView 서버사이드 알림
      │  POST {"secret":"...", "event":"break_up", ...}
      ▼
Cloudflare Worker (worker.js)
      ├─ 시크릿 상수시간 비교
      ├─ KV 중복 제거 (동일 이벤트 90초)
      ├─ 텔레그램 즉시 발송  ← 수 초 내 도달
      └─ GitHub repository_dispatch (PAT)
              ▼
      GitHub Actions (btc.yml)
      record_alert → fetch_btc → build_page → gh-pages
              ▼
      Cloudflare Pages
```

텔레그램을 Worker에서 먼저 쏘는 이유는, Actions 큐 대기(보통 30초~수 분)를
기다리지 않고 알림을 받기 위해서입니다. 페이지 갱신은 그 뒤에 따라옵니다.

---

## 1. GitHub PAT 발급

Settings → Developer settings → Personal access tokens → **Fine-grained tokens**

- Repository access: `OCW-1027/BTC-DESK` 만 선택
- Permissions → Repository permissions → **Contents: Read and write**
- 만료일 설정 후 발급. 토큰 문자열은 이때만 보입니다.

`repository_dispatch`에는 Contents 권한이면 충분합니다. 광범위한 classic 토큰은
피하십시오.

## 2. Cloudflare Worker 배포

Cloudflare 대시보드 → Workers & Pages → Create → Worker

1. 생성 후 **Edit code**에서 `worker.js` 내용을 붙여넣고 Deploy.
2. Settings → **Variables and Secrets**에 아래를 *Secret* 타입으로 추가:

| 이름 | 값 |
|---|---|
| `TV_SECRET` | 임의의 긴 랜덤 문자열 (아래 생성법 참고) |
| `GH_PAT` | 1단계에서 발급한 토큰 |
| `GH_REPO` | `OCW-1027/BTC-DESK` |
| `TG_TOKEN` | 텔레그램 봇 토큰 (선택) |
| `TG_CHAT` | 텔레그램 채팅 ID (선택) |

3. Settings → **Bindings** → KV Namespace 추가:
   - Variable name: `ALERTS`
   - 네임스페이스는 새로 만들어 연결 (이름 예: `btc-desk-alerts`)

KV를 붙이지 않아도 동작하지만, **중복 제거가 비활성화**되어 같은 알림이
반복 발송될 수 있습니다.

시크릿 생성:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

4. 배포 후 URL 확인 (`https://btc-desk-webhook.<계정>.workers.dev`).
   브라우저로 열면 `{"ok":true,...}`가 나와야 정상입니다.

## 3. 동작 확인

```bash
curl -X POST https://<worker-url> \
  -H 'content-type: application/json' \
  -d '{"secret":"발급한_시크릿","event":"break_up","symbol":"BTCUSDT","price":82206,"tf":"4h","note":"테스트"}'
```

- `{"ok":true,"dispatched":true,...}` → 정상
- `401 unauthorized` → 시크릿 불일치
- `dispatched:false` → PAT 또는 GH_REPO 확인
- 같은 요청을 즉시 다시 보내면 `skipped:"duplicate"` (정상 동작)

GitHub Actions 탭에 `BTC Desk` 실행이 뜨는지 확인하십시오.

## 4. Pine Script 적용

1. TradingView 차트 → Pine 에디터 → `btc_desk_alerts.pine` 붙여넣기 → 저장 → 차트에 추가
2. 지표 설정에서 **웹훅 시크릿**에 2단계의 `TV_SECRET` 입력
3. 저항/지지 레벨을 현재 관심 구간으로 조정

> 시크릿이 지표 설정에 들어가므로, **이 스크립트를 절대 공개(Publish)하지 마십시오.**
> Private 저장만 사용하십시오.

## 5. 알림 생성

차트에서 알림 추가(Alt+A):

| 항목 | 설정 |
|---|---|
| Condition | **BTC Desk Alerts** → **Any alert() function call** |
| Options | Once Per Bar Close |
| Expiration | Open-ended (Premium 이상) |
| Notifications | **Webhook URL** 체크 → Worker URL 입력 |
| Message | **비워두거나 그대로 둘 것** |

Message 칸은 무시됩니다. `alert()`가 만든 JSON이 그대로 전송됩니다.

**전제 조건 두 가지:**
- 계정에 **2FA 활성화**가 되어 있어야 웹훅 알림을 쓸 수 있습니다.
- **서버사이드 알림은 Premium 이상**입니다. 그 아래 등급은 브라우저나 앱이 열려
  있어야만 트리거됩니다. PC 독립 운영이 목적이라면 이 조건이 핵심입니다.

## 6. 발신되는 이벤트

| event | 조건 |
|---|---|
| `break_up` | 종가가 저항 레벨 상향 교차 |
| `break_down` | 종가가 지지 레벨 하향 교차 |
| `rsi_ob` / `rsi_os` | RSI 과열/과매도 기준선 교차 |
| `bmsb_lost` / `bmsb_recl` | 불마켓 서포트 밴드 이탈/회복 |
| `vol_spike` | 봉 변화폭이 ATR14 × 배수 초과 |

모두 **종가 확정 기준**입니다. 심지로 인한 오탐을 막기 위한 의도적 선택입니다.

---

## 운영 주의

- **알림 폭주 방지**: Worker의 `DEDUPE_TTL`(기본 90초)이 동일 이벤트를 억제합니다.
  1분봉에 붙이면 이벤트가 과다해지므로 **1시간봉 이상**을 권합니다.
- **Actions 사용량**: 웹훅 1건당 워크플로 1회(약 1~2분)입니다. 이벤트가 하루
  수십 건이면 무료 한도를 잠식할 수 있으니 레벨을 좁게 잡으십시오.
- **레벨 갱신**: Pine의 저항/지지는 수동 입력입니다. 시장 구조가 바뀌면
  `data/latest.json`의 피보나치·BMSB 값을 보고 조정하십시오.
- **시크릿 유출 시**: Worker의 `TV_SECRET`만 교체하고 Pine 설정을 갱신하면 됩니다.
  GitHub PAT은 Worker 내부에만 있으므로 TradingView 쪽으로 노출되지 않습니다.
