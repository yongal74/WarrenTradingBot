# Warren Trading Bot v6.1 — 시장 환경 지표 확장

릴리스 날짜: 2026-05-01
이전 버전: v6.0 (전략 로테이션 기초)

---

## 개요

v6.1은 v6.0의 레짐 감지를 **4→5지표 가중 점수 시스템**으로 강화한다.
- 기존: SPY 200MA / QQQ 50MA / VIX (단순 if/elif)
- v6.1: 위 3지표 + 시장 폭(breadth_pct) + BTC 도미넌스 → 합산 점수

---

## 핵심 변경사항

### 1. 5지표 가중 점수 시스템

| 지표 | 조건 | 점수 |
|------|------|------|
| SPY vs 200MA | ≥+3% | +2 |
| SPY vs 200MA | ≥0% ~ <3% | +1 |
| SPY vs 200MA | <0% | +0 |
| QQQ 50MA 5일 기울기 | ≥+0.3% | +1 |
| VIX | <18 | +2 |
| VIX | 18~25 | +1 |
| VIX | ≥25 | +0 |
| 시장 폭(breadth_pct) | ≥70% | +1 |
| BTC 도미넌스 | <55% (알트 선호) | +1 |
| **합계** | | **0~7점** |

### 2. 레짐 판정 규칙

```
하드 트리거 (점수 무관):
  RISK_OFF: SPY ≤ -2%  OR  VIX ≥ 30

점수 기반:
  TRENDING : 5점 이상
  SIDEWAYS : 2~4점
  RISK_OFF : 1점 이하
```

### 3. `breadth_pct` — 시장 폭 계산

- US 유니버스 종목(최대 10개) 벌크 다운로드
- 각 종목 50MA 위 여부 판단
- `breadth_pct = 50MA 위 종목 수 / 전체 확인 종목 수`

### 4. `btc_dominance` — BTC 도미넌스 추정

```python
# 근사 순환 공급량 사용
mc_btc = BTC_가격 × 19,700,000
mc_eth = ETH_가격 × 120,000,000
mc_sol = SOL_가격 × 460,000,000
btc_dominance = mc_btc / (mc_btc + mc_eth + mc_sol)
```

> 실제 도미넌스(coinmarketcap)와 차이 있을 수 있으나 방향성 파악에 유효

### 5. `_append_regime_history()` — 레짐 히스토리

```
logs/regime_history.json
```

- 매 `_detect_market_regime()` 호출 시 결과 append
- 최대 200개 유지 (FIFO)
- 향후 레짐 변화 추적 / 백테스트에 활용

---

## 반환 dict 구조 (v6.1)

```json
{
  "regime":         "TRENDING",
  "spy_vs_200ma":   3.5,
  "qqq_slope_5d":   0.45,
  "vix_level":      16.2,
  "breadth_pct":    0.8,
  "btc_dominance":  0.52,
  "regime_score":   6,
  "detected_at":    "2026-05-01 09:00:00"
}
```

---

## 예외 처리

- SPY 데이터 부족(≤205봉): 즉시 `UNKNOWN` 반환
- QQQ / VIX / breadth / BTC 조회 실패: 해당 점수 0점 처리 후 계속
- 네트워크 전체 오류: `UNKNOWN` + `error` 필드 반환

---

## 테스트

`tests/test_v61_market_regime.py` — 14개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestRegimeScore` | 7 | 점수 필드 확인, 하드 트리거, TRENDING, UNKNOWN |
| `TestRegimeHistory` | 4 | 파일 생성, append, max 200, 내용 확인 |
| `TestReturnStructure` | 3 | 필수 키 8개, datetime 포맷, regime 유효값 |

실행:
```bash
pytest tests/test_v61_market_regime.py -v
```

---

## 다음 단계 (v6.2)

- **동적 자본 배분 제안**: 시장별/전략별 성과 기반 자본 재배분 제안
- 성과 리포트 + 레짐 데이터 결합 → 자본 배분 비율 제안
- PENDING 상태로 저장, 자동 적용 금지
