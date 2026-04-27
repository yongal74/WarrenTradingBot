# Warren Trading Bot v3.0 — 시스템 종합 문서

> 작성일: 2026-04-27
> 버전: v3.0 (5-Pillar + FVG+OB + 학습 에이전트)
> GitHub: https://github.com/yongal74/WarrenTradingBot

---

## 1. 시스템 개요

```
Warren Bot = FVG+OB 자동 신호 스캐너
           + 5-Pillar 매크로/국면 필터
           + 매일 15:35 복기 학습 에이전트
           + Streamlit 대시보드 (TradingView 스타일)
           + 텔레그램 실시간 알림
```

**운용 자금 (Phase 1 포워드 테스트)**

| 시장 | 시드 | 트레이드당 리스크 | 월 목표 |
|------|------|-----------------|--------|
| 한국주식 | 1,000만원 | 20만원 (2%) | +267만원 |
| 미국주식 | 1,000만원 | 20만원 (2%) | +187만원 |
| 암호화폐 | 500만원 | 10만원 (2%) | +203만원 |
| **합계** | **2,500만원** | | **+657만원** |

---

## 2. 종목 유니버스 (14종목)

### 한국주식 KR (5종목)
| 코드 | 종목명 | 주요 전략 |
|------|--------|---------|
| 005930 | 삼성전자 | FVG + OB |
| 000660 | SK하이닉스 | FVG + OB |
| 009150 | 삼성전기 | OB + FVG |
| 034020 | 두산에너빌리티 | FVG + OB |
| 008060 | 대덕전자 | FVG + OB |

### 미국주식 US (5종목)
| 코드 | 종목명 | 주요 전략 |
|------|--------|---------|
| NVDA | 엔비디아 | FVG |
| PLTR | 팔란티어 | FVG + OB |
| AMD | AMD | FVG + OB |
| TSLA | 테슬라 | FVG + MACD |
| SOXX | 반도체 ETF | FVG + OB |

### 암호화폐 CRYPTO (4종목) — 2026-04-27 추가
| 코드 | 종목명 | yfinance | 주요 전략 |
|------|--------|---------|---------|
| BTC | 비트코인 | BTC-USD | FVG + OB |
| ETH | 이더리움 | ETH-USD | FVG + OB |
| SOL | 솔라나 | SOL-USD | FVG + OB |
| XRP | 리플 | XRP-USD | FVG + MACD |

---

## 3. 5-Pillar 전략 구조

```
┌─────────────────────────────────────────────────────┐
│ Pillar 1  거시 경제 국면 판별                         │
│  VIX / DXY / US10Y / 원달러 / 유가                   │
│  4단계: HALT / DEFENSIVE / NORMAL / AGGRESSIVE       │
│  → HALT시 전면 차단                                   │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Pillar 2  종목 스크리닝                               │
│  14종목 고정 (KR5+US5+CRYPTO4)                       │
│  60일 백테스트 검증 완료                               │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Pillar 3  FVG + Order Block 진입 전략 (핵심)          │
│  S17_FVG: Fair Value Gap 갭 진입                     │
│  S26_OB:  Order Block 수요존 진입                    │
│  타임프레임: 15분봉 진입 / R:R = 1:2                  │
│  백테스트 성과: 평균승률 78.5%, 총수익 +31.76%        │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Pillar 4  진입 품질 점수 (7점 만점)                   │
│  NORMAL/AGGRESSIVE: 필터 없음 (FVG+OB 최고 성과)     │
│  DEFENSIVE:         3점 이상만 진입 허용              │
│  1.RSI<65  2.거래량확인  3.EMA정배열  4.구간신선도    │
│  5.핀바/해머  6.VWAP위  7.스윙로우위                  │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Pillar 5  게이트키퍼 (최종 필터)                      │
│  일일 손실 한도: -6% (3번 손절시 자동 차단)            │
│  주간 손실 한도: -10%                                 │
│  MDD 한도: -20% (봇 자동 정지)                       │
│  최소 R:R: 1:2 (SL 0.1%~1.5%)                       │
└─────────────────────────────────────────────────────┘
```

### Pillar 1 국면별 행동 기준

| 국면 | VIX | Score | 행동 |
|------|-----|-------|------|
| **HALT** | > 35 | - | 전면 거래 차단 |
| **DEFENSIVE** | > 25 | ≥ 5 | FVG+OB + 품질 필터 3점+ |
| **NORMAL** | 20~25 | 2~4 | 순수 FVG+OB (필터 없음) |
| **AGGRESSIVE** | < 20 | < 2 | 순수 FVG+OB (필터 없음) |

---

## 4. 백테스트 결과 (2026-04-27 기준)

### FVG+OB 3종 비교 (15분봉, R:R=1:2)

| 전략 | 유효종목 | 평균승률 | EV/trade | **총수익** |
|------|---------|---------|---------|-----------|
| **A: FVG+OB 단독** | **14/14** | **78.5%** | **+0.73%** | **+31.76%** |
| B: +DBB 필터 | 10/14 | 71.6% | +0.67% | +8.65% |
| C: +DBB+C1 필터 | 4/14 | 87.8% | +1.21% | +6.32% |

> **결론: FVG+OB 단독이 압도적 최고 성과**
> 필터 추가 → 거래횟수 급감 → 총수익 오히려 폭락
> Phase 1 기준: 승률 45%+ 목표 → 현재 78.5%로 훨씬 초과

### 종목별 상세 (FVG+OB 단독)

| 종목 | 거래수 | 승률 | EV/trade | FVG승률 | OB승률 |
|------|-------|------|---------|--------|-------|
| SOL | 52 | **94.2%** | +1.54% | 95.2% | 93.5% |
| XRP | 61 | 78.7% | +1.12% | 70.8% | 83.8% |
| ETH | 58 | 79.3% | +1.08% | 63.2% | 87.2% |
| BTC | 73 | 78.1% | +0.95% | 78.3% | 78.0% |
| 두산에너빌리티 | 40 | 80.0% | +0.88% | 100% | 66.7% |
| NVDA | 8 | 87.5% | +0.28% | 100% | 75.0% |

---

## 5. 매일 복기 루틴 (자동화)

```
09:05  한국장 스캔    → FVG+OB 신호 스캔 → 텔레그램 알림
15:35  복기 + 학습   → 25전략 시뮬 + 5-Pillar 손실 방어 검증 → 텔레그램 리포트
22:35  미국장 스캔    → FVG+OB 신호 스캔 → 텔레그램 알림
```

### 학습 에이전트 동작

1. **25전략 시뮬레이션**: 14종목 × 25전략 = 350가지
2. **14일 롤링 성과**: Sharpe ratio + 승률 기준 자동 랭킹
3. **우선순위 저장**: `config/strategy_priorities.json`
4. **5-Pillar 손실 방어 검증** ← 핵심
   - 최근 14일 손실 거래 추출
   - "Pillar1 (매크로) 가 적용됐다면 차단됐을까?" 계산
   - "Pillar4 (품질점수) 가 적용됐다면 차단됐을까?" 계산
   - 방어율 텔레그램 리포트
5. **전략 변경시 알림**: `이전전략 → 신규전략` 변경 내역 보고

---

## 6. 텔레그램 알림 형식

### 신호 알림
```
[Warren FVG+OB] KR 신호 2건
2026-04-27 09:05
────────────────────────────
두산에너빌리티(034020) [OB]
  현재가=128,800  진입=128,600
  TP=+0.62%  SL=-0.31%
────────────────────────────
R:R = 1:2 | 구간 만료시 신호 취소
```

### 복기 리포트
```
[Warren 복기] 5-Pillar 손실 방어 검증
2026-04-27 | 매크로: [NORMAL]
VIX=19.0  DXY=98.3  US10Y=4.32%  KRW=1471
──────────────────────────────
분석 신호: 18건
  ✅ WIN:  14건
  ❌ LOSS: 2건
  ❓ 미확정: 2건
──────────────────────────────
Pillar 방어 효과:
  Pillar1 (매크로): 1/2 손실 차단 (50%)
  Pillar4 (품질점수): 2/2 손실 차단 (100%)
→ Pillar 스크리닝 효과 검증됨
```

---

## 7. 리스크 관리 원칙

```
트레이드당 리스크: 시드의 2%
  한국 1000만원 → 최대 20만원 손실/trade
  미국 1000만원 → 최대 20만원 손실/trade
  코인  500만원 → 최대 10만원 손실/trade

R:R 최소 1:2 (SL 0.1%~1.5%, TP = SL × 2)

일일 손실 한도: -6% → 3번 손절시 당일 거래 중단
주간 손실 한도: -10%
MDD 한도:      -20% → 봇 자동 정지
```

---

## 8. 투자 단계별 계획

### Phase 1 — 포워드 테스팅 (지금~2주)
- 자금: 2,500만원 (가상/모의)
- 목표: 승률 45%+ 확인 (현재 78.5% 백테스트)
- 매일 복기로 Pillar 신뢰도 검증

### Phase 2 — 실전 투입 (Phase 1 후 1개월)
- 조건: 포워드 테스트 승률 45%+ 2주 연속 확인
- 자금 동일, 리스크 관리 강화
- 월 목표: 400~600만원

### Phase 3 — 스케일업 (3~6개월 후)
- 한국주식: 5,000만원
- 미국주식: 5,000만원
- 코인: 5,000만원
- 월 목표: 3,000~5,000만원

### 수익 현금화 원칙
```
매월 수익 발생시:
  → 50%: 현금 보유 (다음달 운용자금)
  → 50%: 분배형 ETF 매수 (JEPI, JEPQ, QDVO 등)

ETF 매수 타이밍:
  → Market Brain에서 AGGRESSIVE 구간 확인
  → 급락(-5% 이상) 후 반등 초기 매수
```

---

## 9. 로컬 앱 실행 방법

### 최초 설치
```bash
# 1. 다운로드
git clone https://github.com/yongal74/WarrenTradingBot.git
cd WarrenTradingBot

# 2. 설치 (Python 3.11+ 필요)
install.bat

# 3. 환경 설정
메모장으로 .env 열어서 입력:
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
```

### 매일 실행
```
WARREN_START.bat  ← 더블클릭
  → 매크로 국면 체크 (Pillar 1)
  → FVG+OB 즉시 스캔
  → 대시보드 시작 (http://localhost:8501)
  → 브라우저 자동 오픈
```

### 자동화 등록 (최초 1회)
```
setup_scheduler.bat  ← 우클릭 → 관리자로 실행
  → Warren_Scanner_KR  09:05 등록
  → Warren_Learning    15:35 등록
  → Warren_Scanner_US  22:35 등록
```

### 수동 실행
```bash
# 즉시 스캔
run_scanner.bat

# 복기 + 학습
run_learning.bat

# 대시보드만
run_dashboard.bat

# 매크로 국면 확인
python core/macro_regime.py
```

---

## 10. 파일 구조

```
WarrenTradingBot/
├── WARREN_START.bat          ← 메인 런처 (더블클릭)
├── install.bat               ← 최초 설치
├── setup_scheduler.bat       ← Task Scheduler 등록
├── run_scanner.bat           ← 수동 스캔
├── run_learning.bat          ← 수동 복기/학습
├── run_forward_daily.py      ← 포워드 테스트 메인
│
├── config/
│   ├── assets.py             ← 14종목 유니버스
│   ├── settings.py           ← 리스크/시드 파라미터
│   └── strategy_priorities.json  ← 학습 에이전트 결과
│
├── core/
│   ├── fvg_ob_tester.py      ← FVG+OB 스캐너 (Pillar 3)
│   ├── macro_regime.py       ← 매크로 국면 (Pillar 1) ★NEW
│   ├── learning_agent.py     ← 복기 학습 에이전트 ★NEW
│   ├── strategy_factory.py   ← 25개 전략
│   ├── confluence_engine.py  ← C1~C5 합류점
│   ├── risk_manager.py       ← Pillar 5 게이트키퍼
│   └── portfolio_manager.py  ← 포지션 관리
│
├── data/
│   └── data_loader.py        ← yfinance + FDR (CRYPTO 지원)
│
├── dashboard/
│   ├── app.py                ← Streamlit 메인 (다크모드)
│   └── pages/
│       ├── page_overview.py  ← 종합 대시보드
│       ├── page_live.py      ← 라이브 트레이딩
│       ├── page_signals.py   ← FVG+OB 신호
│       ├── page_brain.py     ← Market Brain (5-Pillar)
│       ├── page_analysis.py  ← 차트 분석
│       ├── page_strategy.py  ← 25전략 현황
│       ├── page_trades.py    ← 체결 로그
│       ├── page_backtest.py  ← 백테스트 결과
│       └── page_settings.py  ← 설정
│
├── trading_backtest/
│   ├── backtest_fvg_ob.py    ← FVG+OB 3종 비교
│   └── backtest_3market.py   ← 3시장 통합 백테스트
│
├── tests/
│   ├── test_strategies.py    ← 전략 단위 테스트
│   ├── test_performance.py   ← 성능/리스크 테스트
│   └── test_security.py      ← 보안 테스트
│
├── logs/
│   ├── forward_signals.csv   ← 신호 누적 로그 ★포워드테스트
│   ├── learning_log.csv      ← 학습 에이전트 기록
│   └── trade_log.csv         ← 체결 기록
│
└── .streamlit/
    └── config.toml           ← 다크 테마 설정
```

---

## 11. 현재 시스템 상태 (2026-04-27 21:44)

### 매크로 국면 (Pillar 1)
```
Regime:  NORMAL
VIX:     19.0  (< 20, 정상)
DXY:     98.27
US10Y:   4.32% (주의 수준)
KRW:     1,471 (약세)
WTI:     96.2  (고유가 주의)
Score:   4/10  (NORMAL 유지)
```

### 오늘 포워드 테스트 결과 (첫날)
```
신호 발생: 6건
  KR:     두산에너빌리티(OB), 대덕전자(OB)
  US:     NVDA(FVG), AMD(OB), SOXX(OB)
  CRYPTO: BTC(FVG)  ← 오늘부터 CRYPTO4 추가
텔레그램: 전송 완료
CSV 저장: logs/forward_signals.csv
```

### 테스트 현황
```
40 / 40 PASS  (test_strategies + test_performance + test_security)
GitHub:  https://github.com/yongal74/WarrenTradingBot (최신 커밋 반영)
```

---

## 12. 주요 변경 이력

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-04-27 | v3.0 | CRYPTO4 추가, 5-Pillar, 학습에이전트, 텔레그램 연동 |
| 2026-04-27 | v2.5 | 다크모드 config.toml, st.metric 네이티브, 사이드바 수정 |
| 2026-04-27 | v2.0 | FVG+OB 백테스트 (A/B/C 비교), 리스크 파라미터 업데이트 |
| v2.0 이전 | v1.x | 초기 25전략 팩토리, KR5+US5 포워드 테스트 |

---

*Warren Trading Bot — ICT FVG+OB 기반 자동 매매 시스템*
*매일 복기로 배우고, 5-Pillar로 지키고, FVG+OB로 수익낸다.*
