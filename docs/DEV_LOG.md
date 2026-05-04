# Warren Trading Bot — 개발 로그

---

## 2026-04-28 (Session 4) — Real vs Fake 필터 시스템 + 페이퍼 트레이딩 자금 확대

### 완료된 작업

#### 1. 페이퍼 트레이딩 자금 2억으로 확대
- KR: 5,000만원 (트레이드당 500만)
- US: 5,000만원 (트레이드당 500만)
- CRYPTO: 1억원 (트레이드당 1,000만)
- `run_paper_trading.py` 및 `dashboard/_pages/_page_paper.py` 업데이트
- `paper_portfolio.json`, `paper_positions.json` 리셋

#### 2. 11-Point Quality Score (Real vs Fake 탐지 시스템)
기존 7점 → 11점으로 확장. 핵심은 Fake 신호 제거.

**추가된 4가지 Fake 탐지 필터:**
| 필터 | 탐지 내용 |
|------|---------|
| Vol_Spike | 볼륨 1.5배 이상 급증 (기관 진입 증거) |
| Liq_Sweep | 스윙로우 돌파 후 회복 (기관의 유동성 청소) |
| CHoCH | 구조 전환 확인 (하락 구조 깨고 고점 갱신) |
| Body_In_Zone | 캔들 몸통이 구간 안으로 닫힘 (진짜 수요 확인) |

- `core/fvg_ob_tester.py` `_entry_quality_score()` 11점 시스템 완성
- 트레이드마다 11개 필터 상태 전부 `paper_trades.csv`에 기록

#### 3. Filter Discovery Engine (학습 루프 v2)
`run_learning_loop.py` 완전 재작성. 단순 WR 추적 → 필터별 중요도 발견 엔진으로.

**핵심 기능:**
- `analyze_filters()`: 필터 존재시 vs 부재시 승률 비교 → 중요도 ★★★/★★/★
- `analyze_fake_patterns()`: Fake 신호 공통 패턴 추출 (시간대, 볼륨, 구조)
- `auto_adjust()`: 데이터 30건+ 시 자동 파라미터 조정
  - diff >= 20%p → required_filter로 강제 지정
  - 승률 < 45% → 품질 기준 +1 상향
  - 승률 > 70% → 일일 한도 +2 확대
- `strategy_params.json` 버전 관리 (모든 변경 이력 보존)

#### 4. 문서 완성
- `docs/STRATEGY_FACTORY.md` — 투자 전략 전체 정리 (25전략 + FVG+OB★)
- `docs/LEARNING_STRATEGY.md` (NEW) — 학습 전략 + Real vs Fake 방법론
- `docs/DEV_LOG.md` — 세션별 개발 로그

### 재무 계획 수정 (3억 목표 역산)
| 구분 | 수익률 | 월수익 |
|------|--------|-------|
| 백테스트 FVG+OB★ 4H | ~2.8%/월 | - |
| 3억 × 2% (현실적) | 2% | 600만 |
| 3억 × 3% (좋은 달) | 3% | 900만 |
| 월 2000만 필요 자금 | - | 5~8억 필요 |

**결론**: 3억으로 월 2천은 비현실적. 월 600~900만이 검증된 목표.
현재 고정수입(1,170만/월) + 트레이딩(600~900만) = **1,770~2,070만/월** 도달 가능.

### 2주 모니터링 계획
- Week 1: 데이터 수집 (30~50건 트레이드)
- Week 2: ★★★ 필터 발견, Fake 패턴 확정
- 매일 06:05: 학습 루프 자동 실행 + 리포트 생성

---

## 2026-04-27 (Session 3) — 백테스트 완성 + 페이퍼 트레이딩 셋업

### 완료된 작업

#### 1. 종합 백테스트 시스템
- **파일**: `run_backtest_all.py`
- 14종목 × 25전략 × 4타임프레임 (15m / 5m / 4h / 1m+4h)
- yfinance 실데이터 기반
- 출력: `backtest_results/all_results.csv`, `strategy_ranking.csv`, `top3_per_asset.csv`

**핵심 결과:**
| 전략 | 타임프레임 | 평균수익 | WR | Sharpe |
|------|-----------|---------|-----|--------|
| FVG+OB | 4H | +205.78% | 60% | 0.26 |
| FVG+OB | 15m | +33.76% | 53% | 0.16 |
| FVG+OB | 5m | +34.13% | 48% | 0.13 |

#### 2. FVG+OB★ 필터링 전략 (핵심 개선)
- **파일**: `core/fvg_ob_tester.py`, `run_backtest_all.py`

**필터 조건:**
- 품질 점수 MIN_QUALITY_SCORE = 4 (7점 중)
  - RSI < 65
  - Volume > 20봉 평균
  - EMA 정배열 (9 > 21 > 50)
  - 구간 신선도 (접촉 1회 이하)
  - 핀바/해머 캔들
  - VWAP 위
  - 직전 스윙로우 위
- 하루 5~10건 Flexible (Q6~7 우선, 최대 10건)
- 고유동성 시간대 KST 9~11시 / 22~24시

**필터링 효과:**
| | 원본 | FVG+OB★ |
|--|------|---------|
| 4H Sharpe | 0.26 | 0.37 (+42%) |
| 15m WR | 54% | 57% |
| 15m Sharpe | 0.16 | 0.31 (+94%) |
| 일 거래수 | 15~38건 | 5~10건 |

**코인 4종 (CRYPTO) FVG+OB★ 결과:**
| TF | WR | PnL(기간) | 월평균 |
|----|-----|----------|-------|
| 4H | 61% | +66.76% | ~2.8% |
| 15m | 51% | +13.77% | ~0.6% |
| 4H+15m 병행 | - | - | ~3.5% |

#### 3. 페이퍼 트레이딩 시스템
- **파일**: `run_paper_trading.py`
- 가상자금: KR 5000만 + US 5000만 + CRYPTO 1억 = 2억원 (Session 4에서 확대)
- 포지션 크기: 시장별 10% = KR/US 500만, CRYPTO 1000만/트레이드
- 15분 자동 스캔 (Windows 스케줄러: `WarrenPaperTrade`)
- 로그: `logs/paper_positions.json`, `logs/paper_trades.csv`, `logs/paper_portfolio.json`

#### 4. 학습 루프
- **파일**: `run_learning_loop.py`
- 매일 06:05 자동 실행 (Windows 스케줄러: `WarrenLearningReport`)
- 분석: 시장별/TF별/품질별/시간대별 WR 추적
- 자동 조정: 승률 55% 미만 → 품질 기준 상향 / 70% 이상 → 하향
- 로그: `logs/learning_report.json`, `logs/strategy_params.json`

#### 5. 대시보드 업데이트
- `Paper Trading` 메뉴 추가 (`dashboard/_pages/_page_paper.py`)
- `Backtest Results` — FVG+OB★ 비교 탭 추가 (Tab2)
- 상단 KPI: 필터★ WR, Sharpe, 코인 4H 수익 추가

### 현재 오픈 포지션 (2026-04-27 23:48 시작)
| 종목 | TF | 신호 | 진입가 | Q |
|------|-----|------|--------|---|
| ETH | 4H | OB | 2,320.2 | 6/7 |
| BTC | 4H | FVG | 77,845 | 5/7 |
| TSLA | 4H | OB | 367.63 | - |
| 대덕전자 | 15m | OB | 16,700 | 4/7 |
| 두산에너빌 | 15m | OB | 128,600 | 4/7 |

### 재무 계획 정리
| 단계 | 자금 | 전략 | 목표 월수익 |
|------|------|------|-----------|
| 1단계 (지금~1개월) | 500만~1000만 | 페이퍼 트레이딩 | 데이터 수집 |
| 2단계 (검증 후) | 1.5억 | 코인 4H+15m | 600~900만/월 |
| 3단계 (목표) | 3억 | 코인 4H+15m | 1,200~1,800만/월 |

---

## 2026-04-26 (Session 2) — 5-Pillar 대시보드 + 포워드 스캐너

### 완료된 작업
- 5-Pillar Market Brain 대시보드 (`dashboard/_pages/_page_brain.py`)
- Streamlit 사이드바 자동 네비 제거 (pages/ → _pages/ 폴더 리네임)
- 4H FVG+OB 포워드 스캐너 추가 (`core/fvg_ob_tester.py`)
- Windows UTF-8 인코딩 픽스 (macro_regime.py, learning_agent.py)

---

## 2026-04-25 (Session 1) — 프로젝트 초기 셋업

### 완료된 작업
- 전략 팩토리 25개 전략 구현 (`core/strategy_factory.py`)
- Confluence Engine (`core/confluence_engine.py`)
- 매크로 국면 판단 (`core/macro_regime.py`)
- KIS 트레이더 연동 기반 (`core/kis_trader.py`)
- 텔레그램 알림 (`agents/telegram_agent.py`)
