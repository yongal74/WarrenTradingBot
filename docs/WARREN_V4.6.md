# Warren Trading Bot v4.6 — 시스템 종합 문서

> 작성일: 2026-04-30
> 버전: v4.6 (종목별 전략 레지스트리 / TP1→TP2→TP3 / 7중 방어선)
> 이전 버전: v4.5 (BB반등+Momentum 1H / FVG+OB 4H / 15m 보조지표 3종)

---

## 1. 시스템 개요

```
Warren Bot v4.6 = 종목별 확정전략 레지스트리 (KR 16종목 / US 10종목)
               + FVG+OB 4H CRYPTO 전략 (R:R 1:3)
               + TP1→TP2→TP3 트레일링 청산 전략
               + 15m 보조지표 3종 필터 (EMA정렬+CHoCH+SL정밀화)
               + 7중 방어선 (유니버스/품질/중복/당일재진입/쿨다운/포지션수/일중한도)
               + KIS API 현재가 1순위 (KR)
               + 매일 복기 학습 에이전트
               + Streamlit 대시보드
               + 텔레그램 실시간 알림
```

**운용 자금 (페이퍼 트레이딩)**

| 시장 | 시드 | 포지션/건 | 최대 포지션 | 월 목표 |
|------|------|---------|-----------|--------|
| 한국주식 KR | 5,000만원 | 500만원 | 5개 | +192만원 |
| 미국주식 US | 1억원 | 1,000만원 | 5개 | +267만원 |
| 암호화폐 CRYPTO | 5,000만원 | 500만원 | 5개 | +503만원 |
| **합계** | **2억원** | | **최대 15포지션** | **→1,500만원 목표** |

---

## 2. 종목 유니버스 (30종목)

### 한국주식 KR (16종목)

| 코드 | 종목명 | 섹터 | 확정전략 |
|------|--------|------|---------|
| 005930 | 삼성전자 | 반도체 | BB_SWING |
| 000660 | SK하이닉스 | 반도체 | BB_SWING |
| 009150 | 삼성전기 | 반도체 | BB_SWING |
| 008060 | 대덕전자 | 반도체 | BB_SWING |
| 058470 | 리노공업 | 반도체 | BB_SWING |
| 064350 | 현대로템 | 방산 | BB_SWING |
| 012450 | 한화에어로스페이스 | 방산 | BB_SWING |
| 128940 | 한미약품 | 바이오 | BB_SWING |
| 017670 | SK텔레콤 | 통신 | BB_SWING |
| 035720 | 카카오 | IT | BB_SWING |
| 021240 | 코웨이 | 생활 | BB_SWING |
| 005380 | 현대차 | 자동차 | MOMENTUM |
| 010140 | 삼성중공업 | 조선 | SUPERTREND |
| 086790 | 하나금융지주 | 금융 | MACD |
| 034020 | 두산에너빌리티 | 에너지 | BB_SWING |
| 272210 | 한화시스템 | 방산 | GAPGO |

### 미국주식 US (10종목)

| 티커 | 종목명 | 확정전략 | 백테스트 WR |
|------|--------|---------|-----------|
| AMD | AMD | BB_REVERSAL | 87.5% |
| MU | 마이크론 | SUPERTREND | 80.0% |
| NVDA | 엔비디아 | MACD | 72.7% |
| AVGO | 브로드컴 | SUPERTREND | 66.7% |
| MSTR | 마이크로스트래티지 | BB_MOM | 60.0% |
| LRCX | 램리서치 | BB_MOM | 42.4% |
| AMZN | 아마존 | BB_MOM | 41.0% |
| SHOP | 쇼피파이 | BB_MOM | 38.7% |
| GOOGL | 구글 | BB_MOM | 38.5% |
| TSLA | 테슬라 | MACD | 37.5% |

> ⚠️ 퇴출: PLTR(팔란티어), SOXX(반도체ETF) — v4.6에서 유니버스 외 영구 차단

### 암호화폐 CRYPTO (4종목)

| 티커 | 종목명 | 전략 | R:R |
|------|--------|------|-----|
| BTC | 비트코인 | FVG+OB 4H | 1:3 |
| ETH | 이더리움 | FVG+OB 4H | 1:3 |
| SOL | 솔라나 | FVG+OB 4H | 1:3 |
| XRP | 리플 | FVG+OB 4H | 1:3 |

---

## 3. v4.6 핵심 전략 구조

### 시장별 전략

| 시장 | 메인전략 | TF | 보조(15m) | R:R | 수수료 |
|------|---------|-----|---------|-----|--------|
| KR | 종목별 확정전략 (레지스트리) | 일봉/15m | ✅ 3종 필터 | 1:2 | 0.23% |
| US | 종목별 확정전략 (레지스트리) | 일봉/15m | ✅ 3종 필터 | 1:2 | 0.25% |
| CRYPTO | FVG + OB | 4H | - | 1:3 | 0.10% |

### 종목별 전략 레지스트리 (v4.6 핵심)

```python
# 아키텍처 원칙: 두 곳만 수정하면 전략 추가/변경 완료
_KR_STRATEGY_FN   = { 전략명 → 함수 }   # 함수 레지스트리
_KR_TICKER_STRATEGY = { 종목코드 → 전략명 }  # 종목 매핑

# 예시
'010140' → SUPERTREND  (삼성중공업)
'086790' → MACD        (하나금융)
'272210' → GAPGO       (한화시스템)
```

### 15m 보조지표 3종 필터 (2개 이상 충족 시 진입)

```
① EMA_Align   — 15m EMA 정배열 (단기>중기>장기)
② CHoCH       — 구조전환 (Change of Character) 확인
③ SL정밀화    — SL pct ≤ -1.5% 이내
```

---

## 4. TP1→TP2→TP3 트레일링 청산 전략 (v4.6 신규)

```
진입(entry)
  └─ TP1 = entry + R          ← 초기 목표
       └─ TP2 = entry + 2R    ← 조건 충족 시 연장, SL → TP1
            └─ TP3 = entry + 3R  ← 조건 충족 시 연장, SL → TP2
                 └─ 항상 청산 (연장 없음)
```

**연장 조건 (6가지 체크)**

| # | 조건 | 점수 |
|---|------|------|
| 1 | 일봉 RSI < 75 | +1 |
| 2 | 일봉 MACD 골든크로스 유지 | +1 |
| 3 | 오늘 일봉 양봉 | +1 |
| 4 | 15m EMA 정배열 (4H/daily 포지션만) | +1 |
| 5 | 15m 베어리시 CHoCH 없음 | +1 |
| 6 | 15m RSI > 50 | +1 |

- **TP1→TP2**: 4점 이상 필요
- **TP2→TP3**: 5점 이상 필요
- **CHOCH_EXIT**: TP2 이상 포지션에서 15m 베어리시 CHoCH 감지 → 즉시 청산

---

## 5. 7중 방어선

```
Layer 1: 하드 화이트리스트 (_HARD_WL)
         → 유니버스 외 종목 영구 차단 (PLTR 등)

Layer 2: Quality Score 필터
         → Q4 미만 진입 차단 (이중방어: scan_all + open_positions)

Layer 3: open_ticker_tf 집합
         → 동일 ticker+timeframe 중복 포지션 완전 차단

Layer 4: closed_today 전 타임프레임 차단
         → 당일 청산 종목 재진입 차단 (4H/daily 포함)

Layer 5: tf_cooldowns
         → 4H = 4시간, daily = 24시간 쿨다운

Layer 6: MAX_POS_PER_MARKET = 5
         → 시장별 최대 동시 포지션 수 제한

Layer 7: MAX_DAILY_TRADES = 10
         → 시장별 하루 최대 거래 건수 제한
```

---

## 6. 프로세스 안전 장치 (v4.6 수정)

### Lock 메커니즘 (TOCTOU Race Condition 해결)
```python
# 원자적 배타적 파일 생성으로 동시 실행 완전 차단
with open(LOCK_FILE, 'x') as f:   # 이미 있으면 FileExistsError
    f.write(str(os.getpid()))
```

### CSV 중복 기록 방지
```python
# (ticker, open_time, close_time) 3중 키로 완전 중복 차단
def _is_duplicate_trade(ticker, open_time, close_time) -> bool
```

---

## 7. 5-Pillar 구조

```
Pillar 1: 거시국면 (VIX/DXY/환율) → HALT/DEFENSIVE/NORMAL/AGGRESSIVE
Pillar 2: 종목 스크리닝 (30종목 고정 유니버스)
Pillar 3: 종목별 확정전략 (KR/US 레지스트리) / FVG+OB (CRYPTO)
Pillar 4: 15m 보조지표 3종 품질 필터 + quality_score Q4 이상
Pillar 5: 게이트키퍼 (7중 방어선 + 일 손실 한도 + MDD 한도)
```

### 국면별 행동

| 국면 | VIX | 행동 |
|------|-----|------|
| HALT | >35 | 전면 차단 |
| DEFENSIVE | >25 | 15m 필터 3개 모두 충족 시만 진입 |
| NORMAL | 20~25 | 15m 필터 2개 이상 충족 시 진입 |
| AGGRESSIVE | <20 | 15m 필터 1개 이상 충족 시 진입 |

---

## 8. 리스크 관리

```
트레이드당 포지션: KR 500만원 / US 1,000만원 / CRYPTO 500만원
최대 포지션: 시장별 5개 동시 (전체 최대 15포지션)
일중 거래 한도: 시장별 최대 10건/일
일일 손실 한도: -6% → 자동 차단
MDD 한도: -20% → 봇 자동 정지
오버나이트: KR 금지 (MAX_HOLD 초과 시 강제청산)
           US/CRYPTO 허용 (4H = 최대 15일, 15m = 최대 8시간)
```

---

## 9. 실행 구조

```
paper_trade_scan.bat
  └─ run_master_loop.py (15분 스케줄)
       └─ run_paper_trading.py (실제 거래)
            └─ core/fvg_ob_tester.py (신호 생성)
```

### 주요 파일

```
run_paper_trading.py          ← 페이퍼 트레이딩 메인 (v4.6 핵심 수정)
run_master_loop.py            ← 15분 마스터 루프
core/fvg_ob_tester.py         ← FVG+OB 전략 엔진 + 종목별 레지스트리
version.py                    ← 버전 정보 (4.6.0)
paper_trade_scan.bat          ← 봇 시작 (더블클릭)
logs/paper_portfolio.json     ← 포트폴리오 현황
logs/paper_positions.json     ← 오픈 포지션
logs/paper_trades.csv         ← 청산 거래 기록
logs/master_loop.log          ← 전체 실행 로그
docs/WARREN_V4.6.md           ← 이 문서
```

---

## 10. API 현황

| API | 상태 | 용도 |
|-----|------|------|
| KIS (한국투자) | ✅ 연결 완료 | KR 현재가 1순위 |
| 업비트 | ✅ 연결 완료 | CRYPTO 현재가 1순위 |
| yfinance | ✅ 정상 | US 현재가 / KR·CRYPTO fallback |
| 텔레그램 | ✅ 연결 완료 | 실시간 진입/청산 알림 |

---

## 11. v4.5 → v4.6 변경사항

| 항목 | v4.5 | v4.6 |
|------|------|------|
| KR 전략 | BB반등 공통 | **종목별 확정전략** (레지스트리) |
| US 전략 | BB반등+Momentum 공통 | **종목별 확정전략** (레지스트리) |
| TP 전략 | 단일 TP | **TP1→TP2→TP3 트레일링** |
| 품질 필터 | 부분 적용 | **Q4 이상 이중 방어선** |
| 중복 거래 | 일부 차단 | **7중 방어선 완전 차단** |
| Lock | TOCTOU 취약 | **원자적 파일생성 수정** |
| POSITION_SIZE | KR 500만/US 500만 | **KR 500만/US 1,000만** |
| 유니버스 | PLTR 포함 | **PLTR/SOXX 영구 퇴출** |
| KIS API | fallback | **1순위 현재가** |

---

## 12. 변경 이력

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-04-27 | v3.0 | FVG+OB 5-Pillar, CRYPTO 추가 |
| 2026-04-28 | v4.0 | BB반등 1H 전환, KR 8종목 |
| 2026-04-29 | v4.5 | KR 16종목, US 10종목, 15m 보조 3종 |
| 2026-04-30 | v4.6 | 종목별 전략 레지스트리, TP1→TP3, 7중 방어선, Lock 수정 |

---

*Warren Trading Bot v4.6 — 종목별 최적 전략으로 진입, TP 연장으로 수익 극대화, 7중 방어선으로 리스크 차단*
*시드 2억원 | 월 1,500만원 목표 | 2026-04-30~*
