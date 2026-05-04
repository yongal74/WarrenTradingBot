# Warren Trading Bot v5.2 — ATR 기반 포지션 사이징

릴리스 날짜: 2026-04-30
이전 버전: v5.1 (Circuit Breaker 3단계 + Risk 상수 통합)

---

## 개요

v5.2는 **ATR(Average True Range) 기반 포지션 사이징** 기능을 추가한다.
실전 주문에는 아직 적용하지 않고, 진입 로그에 기존 고정 포지션과 비교하는 참고 정보를 출력한다.

---

## 핵심 변경사항

### 1. `_get_atr(ticker, market, period=14)` — 신규 함수

```python
def _get_atr(ticker: str, market: str = '', period: int = 14) -> float | None:
```

- yfinance 일봉 데이터 60일 다운로드
- True Range = `max(H-L, |H-prevC|, |L-prevC|)`
- ATR(14) = TR의 14일 Rolling Mean
- 반환값: `ATR / 현재가` (소수, 예: `0.03` = 3%)
- 데이터 부족(< 16봉) 또는 ticker 미등록 시 `None` 반환
- 현재가를 `_PRICE_CACHE`에 함께 저장 (중복 API 호출 방지)

### 2. `calc_risk_based_position_size()` — dict 반환으로 변경

#### v5.1 (이전)
```python
def calc_risk_based_position_size(...) -> int:
    return position_krw  # 단일 정수
```

#### v5.2 (현재)
```python
def calc_risk_based_position_size(
    total_equity, entry_price, sl_price,
    risk_pct=None, max_position_krw=None, atr_pct=None
) -> dict:
```

반환 dict:
| 키 | 설명 |
|----|------|
| `sl_based_krw` | SL 거리 기반 권장 포지션 (원) |
| `atr_based_krw` | ATR 기반 권장 포지션 (원, atr_pct 없으면 0) |
| `recommended_krw` | 최종 권장 (ATR 있으면 ATR 기준, 없으면 SL 기준) |
| `risk_krw` | 허용 손실 금액 (total_equity × risk_pct) |
| `sl_pct` | SL 거리 % (예: 2.0 = 2%) |
| `atr_pct_used` | 사용된 ATR% (없으면 0) |

### 3. 포지션 사이즈 3-way 비교 로그

`open_positions()` 진입 시점에 다음 로그를 출력한다:

```
[사이즈] 고정=10,000,000 | SL기반=30,000,000 | ATR기반=20,000,000(ATR=3.0%) | 리스크허용=600,000원
```

- **고정**: 현재 실제 주문에 사용되는 `POSITION_SIZE`
- **SL기반**: `risk_krw / sl_pct` 역산
- **ATR기반**: `risk_krw / atr_pct` 역산 (yfinance 조회 성공 시만)

---

## 핵심 공식

```
risk_krw      = total_equity × risk_pct          # 허용 손실 (기본 0.3%)
sl_pct        = |entry - sl| / entry             # SL 거리 비율
sl_based_krw  = risk_krw / sl_pct               # SL 기반 포지션
atr_based_krw = risk_krw / atr_pct              # ATR 기반 포지션
recommended   = atr_based if atr_pct else sl_based
```

### 예시 (NVDA)
- total_equity = 2억, risk_pct = 0.3% → risk_krw = 60만
- entry = 200, sl = 196 → sl_pct = 2% → sl_based = 3,000만
- ATR = 3% → atr_based = 2,000만
- recommended = 2,000만 (ATR 기준)
- 실제 주문 = 1,000만 (고정)

---

## 설계 원칙

### ATR이 SL보다 더 보수적일 때
- SL이 좁으면 sl_based가 매우 커진다 (ex. SL 0.5% → 1.2억)
- ATR이 실제 변동성을 반영하므로 더 현실적인 사이즈를 제안
- recommended = min(sl_based, atr_based) 효과 → ATR 기준 선택

### ATR이 SL보다 더 공격적일 때
- ATR 변동성이 SL 거리보다 작은 경우 (tight ATR, wide SL)
- recommended = atr_based (ATR 기준 유지)

---

## 실전 적용 계획

| 버전 | 포지션 사이즈 |
|------|------------|
| v5.1 이하 | POSITION_SIZE 고정 |
| v5.2 (현재) | 고정 사용, ATR/SL기반 로그만 출력 |
| v5.3 예정 | 백테스트 결과 기반으로 적용 여부 결정 |

---

## 테스트

`tests/test_v52_atr_sizing.py` — 14개 케이스

| 클래스 | 케이스 수 | 내용 |
|--------|---------|------|
| `TestCalcRiskBasedPositionSizeV52` | 9 | dict 반환 구조, SL/ATR 공식, cap, zero SL |
| `TestGetAtr` | 5 | float 반환, 변동성 비례, 데이터 부족, 미등록 ticker |
| `TestSizingComparison` | 2 | SL<ATR 시나리오, 고정 대비 비교 |

실행:
```bash
pytest tests/test_v52_atr_sizing.py -v
```

---

## 다음 단계 (v5.3)

- **백테스트/성과 엔진**: ticker별/전략별 PF, Expectancy, MDD, Sharpe
- **30일/90일 성과 윈도우** 분석
- `performance_report.json` 자동 생성
- ATR 기반 포지션 사이즈 실전 적용 여부 결정
