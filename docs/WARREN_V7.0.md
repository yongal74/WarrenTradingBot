# Warren Trading Bot v7.0 — AI 운영 에이전트

릴리스 날짜: 2026-05-01
이전 버전: v6.2 (동적 자본 배분 제안)

---

## 개요

v7.0은 **AI 운영 에이전트(AI Ops Agent)**를 추가한다.
포트폴리오, 성과, 레짐, 오픈 포지션을 종합 분석하여 일일 리포트를 생성하고
이상 징후를 감지한다. **거래 실행은 절대 하지 않으며**, 분석과 알림 전용이다.

---

## 핵심 변경사항

### 1. `_detect_anomalies()` — 이상 감지

```python
def _detect_anomalies(pos_data: dict, portfolio: dict) -> list[dict]:
```

| 이상 유형 | 감지 조건 | 심각도 |
|-----------|---------|--------|
| `CONSECUTIVE_LOSS` | 최근 3연속 손실 (HIGH: 5회↑) | HIGH/MEDIUM |
| `SECTOR_CONCENTRATION` | 동일 섹터 MAX_SECTOR_POSITIONS 초과 | MEDIUM |
| `LONG_HOLD` | 단일 포지션 5일 이상 보유 | LOW |
| `LARGE_LOSS_POSITION` | 미실현 손실 -5% 이하 (가격 캐시 활용) | HIGH |

#### 이상 항목 구조

```json
{
  "type":     "CONSECUTIVE_LOSS",
  "severity": "HIGH",
  "message":  "연속 손실 5회 감지 — 전략 점검 권고",
  "detail":   {"streak": 5}
}
```

### 2. `_generate_daily_report()` — 일일 AI 리포트

```python
def _generate_daily_report(pos_data: dict, portfolio: dict) -> dict:
```

#### 리포트 구조

```json
{
  "generated_at": "2026-05-01 09:00:00",
  "date":         "2026-05-01",
  "summary": {
    "total_initial_krw":  200000000,
    "total_current_krw":  202500000,
    "total_realized_pnl": 2500000,
    "return_pct":         1.25,
    "total_trades":       45,
    "win_rate":           62.2,
    "open_positions":     3
  },
  "performance": {
    "all": { ... },
    "30d": { "trades": 12, "win_rate": 66.7, "profit_factor": 2.3, ... },
    "by_market":   { ... },
    "by_strategy": { ... }
  },
  "regime": { "regime": "TRENDING", "vix_level": 15.2, ... },
  "anomalies": [
    { "type": "LONG_HOLD", "severity": "LOW", "message": "034020 6일 보유", ... }
  ],
  "open_positions": [
    { "ticker": "NVDA", "market": "US", "pnl_pct": 2.3 },
    ...
  ],
  "recommendations": [
    "30일 PF < 1.0 — 전략 재검토 필요",
    "RISK_OFF 레짐 — 신규 진입 최소화"
  ]
}
```

#### 저장 위치

```
logs/journal/YYYY-MM-DD-ai_report.json
```

### 3. `step_ai_ops()` — `run_master_loop.py` Step 2d

- 일 1회만 실행 (리포트 파일 존재 여부로 판단)
- `_generate_daily_report()` → JSON 저장 → 텔레그램 전송

### 4. 텔레그램 AI 리포트

```
🤖 Warren AI 일일 리포트 [2026-05-01]
━━━━━━━━━━━━━━━━━━━━
💼 포트폴리오: 202,500,000원 (+1.25%)
📊 누적: 45건 | WR: 62.2%
📈 30d: PF=2.3 | Exp=+25,000원 | MDD=-8.5%
🟢 레짐: TRENDING | VIX=15.2
📂 오픈: 3개 — NVDA(+2.3%), AMD(-0.5%), 034020(+1.2%)
⚠️ 이상 감지 1건:
  🟡 034020 6일 보유 — TP/SL 점검
💡 권고:
  • RISK_OFF 레짐 — 신규 진입 최소화
```

---

## `run_master_loop.py` 전체 파이프라인 (v7.0)

```
Step 1  → 페이퍼 트레이딩 실행
Step 2  → 학습 루프 (10건마다)
Step 2b → 레짐 감지 + 전략 로테이션 제안 (V6.0/6.1)
Step 2c → 동적 자본 배분 제안 (V6.2)
Step 2d → AI 운영 에이전트 (V7.0, 일 1회)
Step 3  → 텔레그램 통합 알림
```

---

## 핵심 원칙: 거래 실행 절대 금지

- `_generate_daily_report()`: `open_positions()` 미호출
- `_detect_anomalies()`: 포지션 조회만, 주문 함수 미호출
- `step_ai_ops()`: subprocess로 `run_paper_trading.py` 재실행 안 함

---

## 테스트

`tests/test_v70_ai_ops.py` — 12개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestDetectAnomalies` | 6 | 정상상태, 연속손실, 장기보유, 키 구조, severity |
| `TestDailyReport` | 6 | 필수 키, JSON 저장, summary 필드, 거래 미실행 확인 |

실행:
```bash
pytest tests/test_v70_ai_ops.py -v
```

---

## 전체 로드맵 완성

| 버전 | 기능 | 상태 |
|------|------|------|
| v5.1 | Circuit Breaker 3단계 + Risk 상수 통합 | ✅ 완료 |
| v5.2 | ATR 기반 포지션 사이징 (참고용) | ✅ 완료 |
| v5.3 | 성과 분석 엔진 (30d/90d/전체) | ✅ 완료 |
| v6.0 | 전략 로테이션 제안 (PENDING) | ✅ 완료 |
| v6.1 | 5지표 시장 환경 확장 + 레짐 히스토리 | ✅ 완료 |
| v6.2 | 동적 자본 배분 제안 (PENDING) | ✅ 완료 |
| v7.0 | AI 운영 에이전트 (일일 리포트 + 이상 감지) | ✅ 완료 |
