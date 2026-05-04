# Warren Trading Bot v6.0 — 전략 로테이션 (마켓 레짐 기반)

릴리스 날짜: 2026-05-01
이전 버전: v5.3 (성과 분석 엔진)

---

## 개요

v6.0은 **마켓 레짐 감지 + 전략 로테이션 제안** 기능을 추가한다.
레짐(TRENDING/SIDEWAYS/RISK_OFF)을 자동 감지하고 최적 전략 우선순위 변경안을 제안한다.
**절대 자동 적용하지 않으며**, PENDING 상태로 저장 후 수동 승인 필수.

---

## 핵심 변경사항

### 1. `_detect_market_regime()` — 레짐 감지

```python
def _detect_market_regime() -> dict:
```

| 지표 | 설명 | 임계값 |
|------|------|--------|
| SPY vs 200MA | 추세 방향 | ≥+2%: 상승 추세, ≤-2%: 하락 |
| QQQ 50MA 5일 기울기 | 모멘텀 강도 | ≥+0.3%: 상향 |
| VIX 현재 수준 | 공포 지수 | <20: 안정, ≥30: 공포 |

#### 레짐 판정 로직

```
RISK_OFF  : SPY ≤ -2%  OR  VIX ≥ 30
TRENDING  : SPY ≥ +2%  AND QQQ_slope ≥ 0.3%  AND VIX < 20
SIDEWAYS  : 그 외 (SPY ±2% 범위 OR VIX 20~30)
```

#### 반환값

```json
{
  "regime":       "TRENDING",
  "spy_vs_200ma": 3.5,
  "qqq_slope_5d": 0.45,
  "vix_level":    16.2,
  "detected_at":  "2026-05-01 09:00:00"
}
```

### 2. `ROTATION_STRATEGY` — 레짐별 전략 우선순위 테이블

| 레짐 | US 1순위 | KR 1순위 | CRYPTO |
|------|---------|---------|--------|
| TRENDING | MACD | MOMENTUM | FVG_OB_4H |
| SIDEWAYS | BB_REVERSAL | BB_SWING | FVG_OB_15M |
| RISK_OFF | SUPERTREND | BB_SWING | **없음** (신규 자제) |

### 3. `_generate_rotation_proposal()` — 제안 생성

```python
def _generate_rotation_proposal(regime_data: dict) -> dict | None:
```

- `performance_report.json`(30d 성과)과 레짐 데이터를 결합
- PENDING 상태 dict 반환
- UNKNOWN 레짐이면 None 반환

#### 제안 구조

```json
{
  "proposed_at": "2026-05-01 09:00:00",
  "status":      "PENDING",
  "type":        "STRATEGY_ROTATION",
  "regime":      "TRENDING",
  "regime_data": { ... },
  "perf_summary": { "trades_30d": 12, "win_rate_30d": 66.7, "pf_30d": 2.3 },
  "proposal": {
    "US_priority":     ["MACD", "BB_MOM", "SUPERTREND", ...],
    "KR_priority":     ["MOMENTUM", "MACD", "BB_SWING", ...],
    "CRYPTO_priority": ["FVG_OB_4H", "FVG_OB_15M"],
    "reason":          "SPY 200MA 위 + QQQ 상향 + VIX<20 → 추세추종 우선"
  },
  "note": "자동 적용 금지 — Claude Code 논의 후 수동 승인 필요"
}
```

### 4. `run_master_loop.py` — `step_regime_rotation()` 추가

- `main()` → Step 2b로 자동 실행
- `strategy_proposals.json`에 PENDING 저장
- 텔레그램 로테이션 제안 알림 발송

### 5. 텔레그램 알림 업그레이드

기본 스캔 리포트에 레짐 정보 추가:
```
🟢 레짐: TRENDING | VIX=15.2 | SPY_200MA=+3.5%
```

별도 로테이션 제안 메시지:
```
🔄 전략 로테이션 제안 [V6.0]
레짐: TRENDING
이유: SPY 200MA 위 + QQQ 상향 + VIX<20 → 추세추종 우선
US 우선순위: MACD → BB_MOM → SUPERTREND
KR 우선순위: MOMENTUM → MACD → BB_SWING
CRYPTO: 정상
🔒 자동 적용 금지
📋 Manual approval required
```

---

## 운영 원칙

### 자동 적용 금지 3중 보호
1. `status: PENDING` — 저장 상태 자체가 대기
2. `note: 자동 적용 금지` — 제안 내부에 명시
3. 텔레그램: "Manual approval required" 메시지

### 승인 절차
1. 텔레그램 알림 수신
2. `logs/strategy_proposals.json` 내용 확인
3. Claude Code와 논의 (전략 효과, 리스크 검토)
4. 수동으로 `core/fvg_ob_tester.py` 수정
5. 제안 status → APPROVED/REJECTED 수동 변경

---

## 테스트

`tests/test_v60_strategy_rotation.py` — 18개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestRotationStrategyStructure` | 6 | 레짐별 키 구조, CRYPTO 빈 목록, 전략 순서 |
| `TestDetectMarketRegime` | 5 | TRENDING/RISK_OFF(VIX)/RISK_OFF(SPY)/SIDEWAYS/UNKNOWN |
| `TestGenerateRotationProposal` | 7 | PENDING 상태, 필수 키, CRYPTO 빈 목록, 자동적용 금지 문구 |

실행:
```bash
pytest tests/test_v60_strategy_rotation.py -v
```

---

## 다음 단계 (v6.1)

- **시장 환경 지표 확장**: SPY 200MA + QQQ 50MA slope + 시장 breadth (상승 종목 비율) + BTC dominance
- VIX 이외 지표 추가로 레짐 감지 정밀도 향상
- 레짐 히스토리 저장 (`regime_history.json`) → 추세 확인
