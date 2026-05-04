# Warren Learning Strategy — 학습 전략 완전 정리

## 핵심 목표: Real vs Fake 진입 타이밍 발견

FVG+OB 신호는 구조적으로 명확하지만, 그 안에서도 **진짜 기관 진입(Real)**과
**가짜 신호(Fake)**를 구분하는 것이 실전 수익률의 핵심이다.

학습 루프(`run_learning_loop.py`)는 매일 06:05 자동 실행되어
**어떤 필터 조합이 Real을 골라내는지** 데이터로 발견한다.

---

## 1. 11-Point Quality Score System

### 기존 7가지 (v1)
| 점수 | 필터 | 의미 |
|------|------|------|
| +1 | RSI < 65 | 과매수 아님 |
| +1 | Volume > 20봉 평균 | 거래량 확인 |
| +1 | EMA9 > EMA21 > EMA50 | 추세 정배열 |
| +1 | 구간 접촉 1회 이하 | 신선한 구간 |
| +1 | 핀바/해머 캔들 | 반전 확인 |
| +1 | Close >= VWAP | 가격 우위 |
| +1 | Entry > 직전 스윙로우 | 구조적 지지 |

### 추가 4가지 (v2 — Fake 탐지)
| 점수 | 필터 | 탐지 패턴 |
|------|------|---------|
| +1 | Vol_Spike | 볼륨 1.5배 이상 급증 (기관 진입 확인) |
| +1 | Liq_Sweep | 스윙로우 돌파 후 즉시 회복 (유동성 청소) |
| +1 | CHoCH | 하락 구조 깨고 고점 갱신 (구조 전환) |
| +1 | Body_In_Zone | 캔들 몸통이 구간 안으로 닫힘 (진짜 수요 확인) |

### 최소 기준
| 국면 | 최소 점수 |
|------|--------|
| HALT | 거래 차단 |
| DEFENSIVE | 6점 이상 |
| NORMAL | 4점 이상 |
| AGGRESSIVE | 4점 이상 |

---

## 2. 학습 루프 작동 구조

### 실행 일정
- **매일 06:05 KST** — Windows Task Scheduler (`WarrenLearningReport`)
- 입력: `logs/paper_trades.csv` (누적 트레이드 기록)
- 출력:
  - `logs/learning_report.json` — 오늘의 분석 결과
  - `logs/strategy_params.json` — 자동 조정된 파라미터 (버전 관리)

### Phase 1: Filter Importance Analysis

각 필터가 **존재할 때 vs 부재할 때** 승률 차이를 계산한다.

```
filter_importance[filter_name] = {
    "present_win_rate": WR when filter=True,
    "absent_win_rate":  WR when filter=False,
    "importance_diff":  present - absent (클수록 중요),
    "n_present":        샘플 수,
    "star_rating":      ★★★ / ★★ / ★ / (중립)
}
```

**중요도 판정:**
- `diff >= 20%p` → ★★★ REQUIRED (해당 필터 없으면 진입 차단)
- `diff >= 10%p` → ★★ HELPFUL
- `diff >= 0%p`  → ★ SLIGHT
- `diff < 0%p`   → 제거 검토

### Phase 2: Fake Pattern Detection

```
fake_patterns = {
    "fake_hours":   승률 40% 미만인 진입 시간대 → excluded_hours에 추가
    "real_hours":   승률 60% 이상인 진입 시간대
    "fvg_vs_ob":    FVG 타입 vs OB 타입 승률 비교
    "vol_ratio":    승리 트레이드 평균 vol_ratio vs 패배 트레이드
    "body_in_zone": Body_In_Zone 유무에 따른 WR 차이
}
```

### Phase 3: Auto-Adjustment

데이터 30건 이상 누적 시 자동 파라미터 조정:

```
1. required_filters 발견  → MIN_QUALITY_SCORE 유지하되 필터 강제화
2. excluded_hours 발견     → LIQUID_HOURS_KST에서 해당 시간 제거
3. overall WR < 45%        → MIN_QUALITY_SCORE += 1
4. overall WR > 70%        → MAX_DAILY_SIGNALS += 2 (더 많은 진입)
5. version 업데이트         → strategy_params.json에 변경 이력 기록
```

---

## 3. 기록되는 트레이드 데이터

`paper_trades.csv`에 매 트레이드마다 아래 정보 저장:

| 컬럼 | 설명 |
|------|------|
| quality_score | 0~11점 |
| quality_tags | 어떤 필터들이 켜졌는지 (예: "rsi,vol,ema,pinbar") |
| entry_hour_kst | KST 진입 시각 |
| vol_ratio | 진입 시 볼륨 / 20봉 평균 볼륨 |
| has_vol_spike | 볼륨 1.5배 이상 여부 |
| has_liq_sweep | 유동성 스윕 여부 |
| has_choch | CHoCH 발생 여부 |
| has_body_in_zone | 몸통 구간 안 닫힘 여부 |
| has_pinbar | 핀바 여부 |
| has_ema_align | EMA 정배열 여부 |
| has_fresh_zone | 신선한 구간 여부 |
| result | WIN / LOSS / OPEN |
| pnl_pct | 수익률 % |

---

## 4. 시간대별 패턴 학습

### 현재 허용 시간대 (초기 설정)
```
KST 09:00~11:00  (한국장 개장)
KST 22:00~24:00  (미국장 개장)
```

### 학습 후 예상 발견 패턴
- 코인: 새벽 2~4시 (아시아 기관 거래 증가) 추가 가능
- KR주식: 9:00~9:30 첫 30분 패닉 구간 제외
- US주식: 22:30~23:30 (개장 초 1시간) 집중
- CHoCH 없는 신호: Fake 비율 높을 것 (예상)

---

## 5. 2주 모니터링 계획

### Week 1 목표: 데이터 수집
- 최소 30~50건 트레이드 기록
- 11개 필터별 기초 데이터 확보
- 명백히 나쁜 시간대 1~2개 발견

### Week 2 목표: 패턴 발견
- 필터 중요도 ★★★ 1~3개 확정
- 승률 45% 미만 시간대 제거
- Fake 패턴 (Body_In_Zone 없는 신호) 승률 확인

### 2주 후 결론
```
[발견 예상]
1. Liq_Sweep + Body_In_Zone 동시 보유 시 WR 65%+
2. Vol_Spike 없는 신호: WR 38% (Fake 다수)
3. CHoCH 없는 4H 신호: Fake 비율 높음
4. KST 10:00~10:30 매수 가장 실패율 낮음 (갭 해소 후 추세)
```

---

## 6. 전략 업그레이드 로드맵

### 현재 (v1): FVG+OB 기본
- 11점 시스템 + 기본 시간 필터
- 페이퍼 트레이딩으로 데이터 수집

### v2 (2주 후): 데이터 기반 필터 확정
- learning_report.json에서 ★★★ 필터 자동 적용
- Fake 판정 로직 강화 (발견된 패턴 반영)

### v3 (1개월 후): 시장별 최적화
- KR / US / CRYPTO 시장별 다른 필터 조합
- 시간대별 Quality 기준 차등 적용

### v4 (2개월 후): 실전 투입 준비
- 페이퍼 WR > 60%, Sharpe > 0.3 확인 후 소액 실전
- KIS API + Upbit API 연동 완료

---

## 7. 핵심 원칙 (불변)

1. **데이터가 전부다**: 직관이 아닌 필터별 승률 수치로 판단
2. **Fake가 Real보다 많다**: 기본 FVG+OB의 Fake 비율은 40~50%. 필터로 줄여야
3. **한 달에 1번 업그레이드**: 너무 자주 바꾸면 overfitting
4. **필터 제거도 중요**: 효과 없는 필터는 과감히 삭제
5. **시장별 다른 특성**: 코인과 한국주식은 Fake 패턴이 다름

---

## 파일 경로

| 파일 | 역할 |
|------|------|
| `run_learning_loop.py` | 학습 루프 메인 |
| `logs/paper_trades.csv` | 트레이드 원본 데이터 |
| `logs/learning_report.json` | 일별 분석 결과 |
| `logs/strategy_params.json` | 자동 조정 파라미터 (버전 관리) |
| `core/fvg_ob_tester.py` | 스캐너 (필터 적용) |
| `dashboard/_pages/_page_paper.py` | 대시보드 Paper 탭 |
