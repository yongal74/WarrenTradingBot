# WarrenTradingActivebot

> AI-powered trading bot — 25 strategies × 15 assets
> Backtesting → Forward Testing → Live Trading pipeline
> TradingView webhook integration | Streamlit dashboard | Telegram alerts

---

## 빠른 시작 (Quick Start)

### 1. 다운로드
```bash
git clone https://github.com/yongal74/WarrenTradingActivebot.git
cd WarrenTradingActivebot
```

### 2. 설치
```
install.bat  (더블클릭)
```

### 3. 설정
`.env` 파일 열어서 입력:
```env
PAPER_CAPITAL=10000000        # 초기 가상 자금
TELEGRAM_BOT_TOKEN=...        # 텔레그램 알림 (선택)
TELEGRAM_CHAT_ID=...
WEBHOOK_SECRET=warren2024     # TradingView 웹훅 보안키
```

### 4. 실행
| 파일 | 설명 |
|---|---|
| `run_dashboard.bat` | 대시보드 → http://localhost:8501 |
| `run_bot.bat` | 1회 수동 실행 |
| `run_webhook.bat` | TradingView 웹훅 서버 |
| `run_ngrok.bat` | 외부 노출 (TradingView 연동) |

---

## 주요 기능

### 전략 (25개)
EMA Cross, Golden Cross, SuperTrend, Hull MA, Ichimoku, RSI Trend/Rev, MACD, Bollinger Bands, ATR Breakout, Donchian, Z-Score, FVG, MSB, CHoCH, Volume Break, EMA Ribbon, Pin Bar, Engulfing, Inside Bar, Monday Effect 등

### 종목 (15개)
**해외 ETF:** JEPI, JEPQ, QDVO, JFLI, ULTY, QQQI
**미국 주식:** NVDA, PLTR, QQQ, SOXX, SPY, TSLA
**국내 ETF:** KODEX테슬라커버드콜(475080), KODEX200위클리커버드콜(498400), TIGER배당커버드콜(472150)

### 리스크 관리
- 단일 포지션 최대 10%
- 일일 손실 -2% → 당일 거래 중단
- 주간 손실 -5% → 주간 거래 중단
- MDD -15% → 봇 자동 정지
- 개별 손절선 -7%

---

## TradingView 연동

**1. 웹훅 서버 실행**
```
run_webhook.bat   (포트 8080)
run_ngrok.bat     (ngrok으로 외부 노출)
```

**2. TradingView Alert 설정**
- Alert URL: `https://xxxx.ngrok-free.app/webhook`
- Message:
```json
{
  "ticker":   "NVDA",
  "action":   "BUY",
  "strategy": "S01_EMA9_21",
  "price":    "{{close}}",
  "secret":   "warren2024"
}
```

---

## 대시보드 (7페이지)

| 페이지 | 내용 |
|---|---|
| Overview | 총 자산, 수익률, MDD, 실시간 신호 |
| Market Brain | Bull/Bear/Neutral 시장 판단 |
| Strategy Factory | 25전략 × 전종목 신호 히트맵 |
| Backtest Results | 종목별 전략 순위 |
| Asset Analysis | 캔들차트 + RSI + MACD |
| Trade Log | 매매 이력, P&L |
| Settings | 설정 확인, TradingView 가이드 |

---

## 로드맵

- [x] 백테스팅 (25전략 × 15종목)
- [x] Paper Trading (Forward Testing)
- [x] Streamlit 대시보드
- [x] TradingView 웹훅 연동
- [x] Telegram 알림
- [ ] Alpaca API 실거래 연동
- [ ] KIS API 한국 주식 실거래 연동

---

## 주의사항

> 이 봇은 교육 목적으로 제작되었습니다.
> 실거래 투입 전 반드시 1개월 이상 Paper Trading으로 검증하세요.
> 투자 손실에 대한 책임은 사용자 본인에게 있습니다.
