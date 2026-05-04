# Warren Trading Bot v5.3 — 성과 분석 엔진

릴리스 날짜: 2026-05-01
이전 버전: v5.2 (ATR 기반 포지션 사이징)

---

## 개요

v5.3은 **성과 분석 엔진(Performance Report Engine)**을 추가한다.
`paper_trades.csv`를 자동 분석하여 30일/90일/전체 기간 × ticker별/전략별 성과 지표를 계산하고 `performance_report.json`에 저장한다.

---

## 핵심 변경사항

### 1. `PERF_REPORT_FILE` — 경로 상수 추가

```python
PERF_REPORT_FILE = LOG_DIR / 'performance_report.json'
```

### 2. `_compute_performance_report()` — 신규 함수

```python
def _compute_performance_report() -> dict:
```

#### 반환 구조

```json
{
  "generated_at": "2026-05-01 09:00:00",
  "windows": {
    "all": { ... metrics ... },
    "90d": { ... metrics ... },
    "30d": { ... metrics ... }
  },
  "by_ticker": {
    "NVDA": { ... metrics ... },
    "AMD":  { ... metrics ... }
  },
  "by_strategy": {
    "MACD":        { ... metrics ... },
    "BB_REVERSAL": { ... metrics ... }
  }
}
```

#### metrics 구조

| 필드 | 설명 |
|------|------|
| `trades` | 총 거래 수 |
| `win_rate` | 승률 (%) |
| `profit_factor` | 총이익 / 총손실 (inf if 전부 WIN) |
| `expectancy_krw` | 기대값 = WR×avgW − LR×avgL (원) |
| `avg_win_krw` | 평균 이익 거래 (원) |
| `avg_loss_krw` | 평균 손실 거래 절댓값 (원) |
| `sharpe` | 거래 단위 Sharpe (mean/stdev) |
| `max_drawdown_pct` | 최대 낙폭 % (음수, 자본 곡선 기반) |

### 3. `_save_perf_report()` — JSON 저장 보조 함수

```python
def _save_perf_report(report: dict) -> None:
```

### 4. `run_once()` 자동 호출 + 요약 출력

```
  [성과-전체] PF=2.5 | Exp=+25,000원 | Sharpe=0.312 | MDD=-8.5%
  [성과-30d] 거래=12건 | WR=66.7% | PF=3.0 | Exp=+30,000원
```

---

## 윈도우 필터링 로직

- `close_time` 기준으로 날짜 필터 적용
- `all`: 전체 기간 (필터 없음)
- `90d`: 최근 90일 이내 close_time
- `30d`: 최근 30일 이내 close_time

---

## 성과 지표 공식

### Profit Factor
```
PF = sum(wins) / abs(sum(losses))
   = inf  if no losses
   = 0.0  if no wins and no losses
```

### Expectancy (거래당 기대 수익)
```
Exp = (win_count/n) × avg_win - (loss_count/n) × avg_loss
```

### Sharpe (거래 단위)
```
Sharpe = mean(pnls) / stdev(pnls)
```
> 일반 연환산 Sharpe와 다름. 거래 일관성 지표로 사용.

### MDD (자본 곡선 기반)
```
cumulative_equity = cumsum(pnl_krw 순서대로)
MDD% = (trough - peak) / peak × 100
```

---

## 파일 위치

| 파일 | 설명 |
|------|------|
| `logs/paper_trades.csv` | 입력 원본 (청산 거래 기록) |
| `logs/performance_report.json` | 출력 (run_once() 실행마다 갱신) |

---

## 테스트

`tests/test_v53_performance.py` — 14개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestWindowFiltering` | 3 | 30d/90d/all 필터 검증 |
| `TestMetricsFormula` | 5 | PF/WR/Expectancy/MDD/all-WIN |
| `TestBreakdown` | 3 | ticker별/전략별 분류 |
| `TestEdgeCases` | 4 | CSV 없음/빈 윈도우/JSON 저장/날짜 포맷 |

실행:
```bash
pytest tests/test_v53_performance.py -v
```

---

## 다음 단계 (v6.0)

- **전략 로테이션**: 트렌드/횡보/리스크 레짐 → 전략 우선순위 변경
- 제안만 생성 (PENDING 상태), 자동 적용 금지
- `strategy_proposals.json`에 저장 후 텔레그램 알림
