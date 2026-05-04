# Warren Trading Bot v6.2 — 동적 자본 배분 제안

릴리스 날짜: 2026-05-01
이전 버전: v6.1 (시장 환경 지표 확장)

---

## 개요

v6.2는 **동적 자본 배분 제안(Capital Allocation Proposal)** 기능을 추가한다.
30일 시장별 성과 데이터와 레짐 판단을 결합하여 KR/US/CRYPTO 자본 배분 비율 변경안을 생성한다.
**절대 자동 적용하지 않으며**, PENDING 상태로 저장 후 수동 승인 필수.

---

## 핵심 변경사항

### 1. `_generate_capital_allocation_proposal()` — 신규 함수

```python
def _generate_capital_allocation_proposal(regime_data: dict) -> dict | None:
```

#### 성과 점수 계산

```
market_score = WR/100 × 0.4 + min(PF,5)/5 × 0.4 + (Exp>0 ? 0.2 : 0)
```

| 비중 | 지표 | 설명 |
|------|------|------|
| 40% | 승률(WR) | 승/패 비율 |
| 40% | 수익률(PF) | 최대 5.0 상한 (inf 방지) |
| 20% | Expectancy 부호 | 양수면 +0.2 |

#### 레짐 오버라이드

| 레짐 | 효과 |
|------|------|
| RISK_OFF | CRYPTO 점수 × 0.3 (대폭 축소) |
| TRENDING | US 점수 × 1.2 (추세 가중) |
| SIDEWAYS | 점수 그대로 |

#### 제약 조건

- 각 시장: 현재 배분 대비 **±20%p** 이내 클리핑
- 합계: 정규화하여 항상 **100%** 유지

#### 현재 배분 기준

```python
INITIAL_CAPITAL = {'KR': 50_000_000, 'US': 100_000_000, 'CRYPTO': 50_000_000}
# KR: 25% / US: 50% / CRYPTO: 25%
```

#### 반환값

```json
{
  "proposed_at":    "2026-05-01 09:00:00",
  "status":         "PENDING",
  "type":           "CAPITAL_ALLOCATION",
  "regime":         "TRENDING",
  "current_alloc":  {"KR": 25.0, "US": 50.0, "CRYPTO": 25.0},
  "proposed_alloc": {"KR": 22.0, "US": 55.0, "CRYPTO": 23.0},
  "diff_pct":       {"KR": -3.0, "US": +5.0, "CRYPTO": -2.0},
  "market_scores":  {"KR": 0.52, "US": 0.71, "CRYPTO": 0.48},
  "note":           "자동 적용 금지 — INITIAL_CAPITAL/POSITION_SIZE 수동 수정 필요"
}
```

### 2. `step_capital_allocation()` — `run_master_loop.py` Step 2c

- 15분 루프마다 실행
- `_generate_capital_allocation_proposal()` 호출
- `strategy_proposals.json`에 PENDING 저장
- 텔레그램 배분 제안 알림 발송

### 3. 텔레그램 메시지

```
💰 자본 배분 제안 [V6.2]
━━━━━━━━━━━━━━━━━━━━
레짐: TRENDING
현재 → 제안 (변화)
  KR:     25.0% → 22.0% (-3.0%)
  US:     50.0% → 55.0% (+5.0%)
  CRYPTO: 25.0% → 23.0% (-2.0%)

🔒 자동 적용 금지
📋 INITIAL_CAPITAL 수동 수정 필요
```

---

## 승인 및 적용 절차

1. 텔레그램 알림 수신
2. `logs/strategy_proposals.json` 확인 (`type: CAPITAL_ALLOCATION`)
3. Claude Code와 논의 (시장 상황, 리스크 검토)
4. 수동으로 `run_paper_trading.py` `INITIAL_CAPITAL` / `POSITION_SIZE` 수정
5. 제안 `status: APPROVED` 수동 변경

---

## 예외 처리

- `performance_report.json` 없거나 `by_market` 비어 있으면 `None` 반환 (제안 생략)
- 모든 시장 성과 데이터 0건: 균등 배분(33/33/33) 제안
- PF = inf인 경우: 5.0으로 상한 처리 (점수 계산 정상화)

---

## 테스트

`tests/test_v62_capital_allocation.py` — 12개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestAllocationProposal` | 6 | None 반환 조건, PENDING, 필수 키, 자동적용금지 |
| `TestAllocationConstraints` | 3 | 합계 100%, ±20%p, 3개 시장 포함 |
| `TestRegimeEffect` | 2 | RISK_OFF CRYPTO 축소, TRENDING US 가중 |

실행:
```bash
pytest tests/test_v62_capital_allocation.py -v
```

---

## 다음 단계 (v7.0)

- **AI 운영 에이전트**: 일일 리포트 + 리스크 알림 + 이상 감지
- 거래 실행 절대 금지, 분석/알림 전용
- LLM(Claude) 기반 자연어 리포트 생성
