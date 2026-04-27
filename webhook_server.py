# -*- coding: utf-8 -*-
"""
TradingView Webhook 서버
- TradingView Alert → POST /webhook → 자동매매 실행
- 실행: python webhook_server.py
- 포트: 8080 (ngrok으로 외부 노출)

TradingView Alert 메시지 형식 (JSON):
{
  "ticker":   "NVDA",
  "action":   "BUY",        # BUY / SELL
  "strategy": "S02_EMA20_50",
  "price":    "{{close}}",
  "secret":   "your_webhook_secret"
}
"""
import sys, io, os, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from datetime import datetime

from core.forward_tester import ForwardTester
from data.data_loader import load
from config.assets import ALL_ASSETS
from config.settings import LOG_DIR

app = FastAPI(title="WarrenTradingActivebot Webhook", version="1.0")

WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'warren2024')
ft = ForwardTester()

# ── 웹훅 수신 로그 ────────────────────────────────────────────
WEBHOOK_LOG = LOG_DIR / 'webhook.log'

def _log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(WEBHOOK_LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


@app.get("/")
def health():
    return {"status": "ok", "bot": "WarrenTradingActivebot", "time": datetime.now().isoformat()}


@app.post("/webhook")
async def webhook(request: Request):
    """TradingView → 이 엔드포인트로 Alert 전송"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 보안 검증
    if body.get('secret') != WEBHOOK_SECRET:
        _log(f"REJECTED: 잘못된 secret from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid secret")

    ticker   = body.get('ticker', '').upper()
    action   = body.get('action', '').upper()   # BUY / SELL
    strategy = body.get('strategy', 'TV_SIGNAL')
    price_raw= body.get('price', '')

    if not ticker or action not in ('BUY', 'SELL'):
        raise HTTPException(status_code=400, detail="ticker, action(BUY/SELL) 필수")

    # 종목 확인
    asset = ALL_ASSETS.get(ticker)
    if not asset:
        _log(f"UNKNOWN ticker: {ticker}")
        return JSONResponse({"ok": False, "msg": f"Unknown ticker: {ticker}"})

    # 현재가 (TV 전달값 우선, 없으면 yfinance)
    try:
        price = float(str(price_raw).replace(',', ''))
    except Exception:
        df = load(ticker, asset['market'])
        price = float(df['Close'].iloc[-1]) if df is not None else 0

    if price <= 0:
        return JSONResponse({"ok": False, "msg": "가격 조회 실패"})

    # Circuit Breaker 체크
    ok, reason = ft.rm.check()
    if not ok:
        _log(f"CIRCUIT BREAKER: {reason}")
        return JSONResponse({"ok": False, "msg": f"Circuit Breaker: {reason}"})

    # 매매 실행
    result = {}
    name = asset['name']

    if action == 'BUY':
        if ft.pm.has_position(ticker):
            msg = f"{ticker} 이미 보유 중 — 매수 건너뜀"
            _log(msg)
            return JSONResponse({"ok": True, "msg": msg})

        qty = ft.rm.position_size(price)
        trade = ft.pm.buy(ticker, price, qty, strategy, name)
        if trade:
            ft.tg.notify_buy(ticker, name, strategy, price, qty, price * qty)
            result = {"action": "BUY", "qty": qty, "price": price, "amount": price * qty}
            _log(f"BUY {ticker} x{qty} @ {price:.2f} [{strategy}]")

    elif action == 'SELL':
        if not ft.pm.has_position(ticker):
            msg = f"{ticker} 포지션 없음 — 매도 건너뜀"
            _log(msg)
            return JSONResponse({"ok": True, "msg": msg})

        trade = ft.pm.sell(ticker, price, reason='TV_웹훅')
        if trade:
            ft.rm.record_pnl(trade['pnl_pct'] / 100)
            ft.tg.notify_sell(ticker, name, strategy, price, trade['qty'],
                              trade['pnl'], trade['pnl_pct'], 'TV웹훅')
            result = {"action": "SELL", "qty": trade['qty'],
                      "price": price, "pnl_pct": trade['pnl_pct']}
            _log(f"SELL {ticker} x{trade['qty']} @ {price:.2f} PnL={trade['pnl_pct']:+.2f}%")

    return JSONResponse({"ok": True, "ticker": ticker, **result})


@app.get("/status")
def status():
    """현재 포트폴리오 상태 조회"""
    try:
        prices = {}
        for tkr, asset in ALL_ASSETS.items():
            df = load(tkr, asset['market'])
            if df is not None:
                prices[tkr] = float(df['Close'].iloc[-1])
        summary = ft.pm.summary(prices)
        return {"ok": True, "portfolio": summary, "positions": ft.pm.positions()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == '__main__':
    port = int(os.getenv('WEBHOOK_PORT', '8080'))
    print(f"\n{'='*50}")
    print(f"  WarrenBot Webhook Server")
    print(f"  http://localhost:{port}/webhook")
    print(f"  TradingView Alert URL: <ngrok_url>/webhook")
    print(f"  Secret: {WEBHOOK_SECRET}")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
