# Warren Trading Bot v5.1 — 시스템 종합 문서

> 작성일: 2026-05-01
> 버전: v5.1 (리스크 엔진 강화 / 코드-문서 정합성 완성)
> 이전 버전: v5.0 (Circuit Breaker / 섹터 집중도 / 포트폴리오 메트릭 도입)

---

## 1. v5.0 → v5.1 핵심 변경사항

| 항목 | v5.0 | v5.1 |
|------|------|------|
| 종목 수 표기 | 코드 주석 27종목(오류) | **30종목 (KR16+US10+CRYPTO4) 정합** |
| 일일 손익 기준 | 실현 손익만 | **실현 + 미실현 손익 합산** |
| 주간 손실 한도 | 구현 없음 | **-5% (월요일 00:00 이후 CSV 집계)** |
| MDD 계산 | initial_capital 대비 | **Peak Equity 기준 진짜 MDD** |
| 현재가 조회 | 매 호출 API | **2분 TTL 캐시 (_PRICE_CACHE)** |
| 포지션 사이징 | 고정 금액만 | **calc_risk_based_position_size() 추가 (참고용)** |
| 포트폴리오 메트릭 | 전체 합산만 | **시장별 + 전략별 breakdown** |
| 상수 관리 | 일부 하드코딩 | **settings.py 단일화 완성** |
| Learning Agent | PENDING 저장 | **Manual approval required 텔레그램 추가** |

---

## 2. 시스템 개요

```
Warren Bot v5.1 = v5.0 전체 기능
               + Weekly Loss Limit (-5%)
               + Peak Equity 기반 MDD (-10%)
               + 미실현손익 포함 Daily Circuit Breaker (-1.5%)
               + 현재가 2분 캐시 (API 호출 최소화)
               + Risk-based Position Sizing 함수 (참고용)
               + 포트폴리오 메트릭 전체/시장별/전략별 확장
               + 코드-문서 완전 정합 (30종목)
```

**운용 자금**

| 시장 | 시드 | 포지션/건 | 최대 포지션 |
|------|------|---------|-----------|
| KR (16종목) | 5,000만원 | 500만원 | 5개 |
| US (10종목) | 1억원 | 1,000만원 | 5개 |
| CRYPTO (4종목) | 5,000만원 | 500만원 | 5개 |
| **합계** | **2억원** | | **최대 15포지션** |

---

## 3. 리스크 엔진 v5.1

### 3-1. Circuit Breaker 3단계 (우선순위 순)

```
① Daily Loss Circuit Breaker
   기준: 오늘 실현PnL + 미실현PnL (오픈 포지션 현재가 조회)
   한도: initial_capital 대비 -1.5%
   조치: 신규 진입 차단 (기존 포지션 SL/TP 체크 계속)

② Weekly Loss Circuit Breaker (V5.1 신규)
   기준: paper_trades.csv 이번주 월요일 00:00 이후 pnl_krw 합산
   한도: initial_capital 대비 -5.0%
   조치: 이번 주 신규 진입 차단

③ MDD Circuit Breaker (V5.1 강화)
   기준: current_equity / peak_equity - 1
         current_equity = 가용자금 + 오픈포지션원금 + 미실현손익
         peak_equity    = portfolio.json['peak_equity'] (누적 최고점)
   한도: -10.0%
   조치: 봇 자동 정지 (신규 진입 차단)
```

### 3-2. Peak Equity 계산 방식

```python
current_equity = sum(capital.values())       # 가용 현금
              + sum(pos['size_krw'])          # 오픈 포지션 원금 (청산 전)
              + unrealized_pnl               # 미실현 손익

if current_equity > peak_equity:
    peak_equity = current_equity             # 신고점 갱신
    portfolio['peak_equity'] = peak_equity   # JSON 저장

mdd_pct = current_equity / peak_equity - 1
```

### 3-3. Risk-based Position Sizing (참고용)

```python
def calc_risk_based_position_size(
    total_equity, entry_price, sl_price,
    risk_pct=RISK_PER_TRADE_PCT,  # 0.003 (0.3%)
    max_position_krw=None
) -> int:
    risk_krw = total_equity * risk_pct
    sl_pct = abs(entry_price - sl_price) / entry_price
    position_krw = risk_krw / sl_pct
    return int(min(position_krw, max_position_krw or position_krw))
```

- 실제 주문은 기존 `POSITION_SIZE` (KR 500만 / US 1,000만 / CRYPTO 500만) 유지
- 진입 로그에 `권장ATR: {recommended_krw}원` 병기 → 추후 v5.2에서 실제 적용 검토

---

## 4. 포트폴리오 메트릭 구조 (V5.1 확장)

`logs/paper_portfolio.json` → `"metrics"` 키:

```json
{
  "metrics": {
    "overall": {
      "total_trades": 50,
      "win_rate": 52.0,
      "profit_factor": 1.45,
      "expectancy_krw": 35000,
      "sharpe": 0.42,
      "max_drawdown_pct": -4.8,
      "avg_win_krw": 180000,
      "avg_loss_krw": 95000
    },
    "by_market": {
      "KR":     {"trades": 20, "win_rate": 55.0, "profit_factor": 1.6, "expectancy_krw": 42000},
      "US":     {"trades": 18, "win_rate": 50.0, "profit_factor": 1.3, "expectancy_krw": 28000},
      "CRYPTO": {"trades": 12, "win_rate": 50.0, "profit_factor": 1.5, "expectancy_krw": 32000}
    },
    "by_strategy": {
      "OB":  {"trades": 30, "win_rate": 53.3, "profit_factor": 1.5, "expectancy_krw": 38000},
      "FVG": {"trades": 20, "win_rate": 50.0, "profit_factor": 1.4, "expectancy_krw": 30000}
    }
  }
}
```

---

## 5. 현재가 캐시 (_PRICE_CACHE)

```python
_PRICE_CACHE: dict = {}   # {ticker: (price, timestamp)}
_PRICE_CACHE_TTL = 120    # 2분

# check_positions() → _get_price() → 캐시 저장
# _check_circuit_breaker() → _get_price() → 캐시 재사용 (중복 API 호출 없음)
```

**효과:**
- 15포지션 기준 기존: ~30 API 호출/사이클
- v5.1: ~15 API 호출 (첫 번째 check_positions에서 캐시, 나머지 재사용)

---

## 6. 8중 방어선 (v5.1 유지)

```
Layer 1: 하드 화이트리스트 — 유니버스 30종목 외 영구 차단
Layer 2: Quality Score ≥ 4 (이중방어)
Layer 3: open_ticker_tf — 동일 ticker+timeframe 중복 차단
Layer 4: closed_today — 당일 청산 종목 재진입 차단
Layer 5: tf_cooldowns — 4H=4시간, daily=24시간
Layer 6: MAX_POS_PER_MARKET = 5
Layer 7: MAX_DAILY_TRADES = 10
Layer 8: 섹터 집중도 — 동일 섹터 최대 2포지션
+ Circuit Breaker (Daily/Weekly/MDD) — 전체 신규 진입 차단
```

---

## 7. 리스크 상수 단일화 (`config/settings.py`)

```python
DAILY_LOSS_LIMIT     = -0.015   # 일일 손실 -1.5%
WEEKLY_LOSS_LIMIT    = -0.05    # 주간 손실 -5%
MDD_LIMIT            = -0.10    # MDD -10%

MAX_SECTOR_POSITIONS = 2        # 동일 섹터 최대 포지션 (V5.1 추가)
RISK_PER_TRADE_PCT   = 0.003    # Risk-based sizing 기준 0.3% (V5.1 추가)
```

모든 코드는 `config/settings.py`에서 import — **파일 내 하드코딩 없음**

---

## 8. Learning Agent 자동 적용 금지

```
학습 결과 → strategy_proposals.json (status: PENDING)
→ 텔레그램 알림:
  "🔒 자동 적용 금지 — strategy_registry 자동 수정 불가"
  "📋 Manual approval required"
  "⚠️ Claude Code에서 논의 후 수동 승인 필요"

strategy_registry 자동 수정 절대 금지
반드시 사람이 코드 리뷰 후 수동 적용
```

---

## 9. 실행 파일 구조

```
paper_trade_scan.bat
  └─ run_master_loop.py (15분 스케줄)
       └─ run_paper_trading.py
            ├─ check_positions()        ← SL/TP + 현재가 조회 → 캐시 저장
            ├─ scan_all()               ← 신호 스캔 (fvg_ob_tester.py)
            ├─ _check_circuit_breaker() ← Daily/Weekly/MDD 3단계 (캐시 재사용)
            └─ open_positions()         ← 8중 방어선 + 권장 사이즈 로그
                 └─ _save_portfolio()   ← peak_equity 갱신 + 메트릭 계산
```

---

## 10. 변경 이력

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-04-27 | v3.0 | FVG+OB 5-Pillar, CRYPTO 추가 |
| 2026-04-28 | v4.0 | BB반등 1H 전환, KR 8종목 |
| 2026-04-29 | v4.5 | KR 16종목, US 10종목, 15m 보조 3종 |
| 2026-04-30 | v4.6 | 종목별 전략 레지스트리, TP1→TP3, 7중 방어선 |
| 2026-05-01 | v5.0 | Circuit Breaker, 섹터 집중도, 포트폴리오 메트릭 |
| 2026-05-01 | v5.1 | Weekly CB, Peak Equity MDD, 미실현PnL, 가격캐시, ATR sizing |

---

## 11. v5.2 로드맵

- **ATR 기반 실제 포지션 사이징**: `calc_risk_based_position_size()` 실전 적용
- **포트폴리오 상관관계 모니터링**: 오픈 포지션 간 beta/correlation 추적
- **전략 로테이션**: SP500 추세 + 시장 폭으로 모멘텀/평균회귀 전략 자동 전환
- **대시보드 메트릭 시각화**: Sharpe/PF/Expectancy 차트

---

*Warren Trading Bot v5.1 — 코드-문서 완전 정합 | 3단계 Circuit Breaker | 2억 운용 | 2026-05-01~*
