# -*- coding: utf-8 -*-
"""
Warren KR 자동매매 (모의투자)
FVG+OB 15분봉 신호 감지 -> KIS 모의투자 자동 주문
15분마다 스캔, 09:00~14:30 운용, 14:55 강제청산

실행: python run_kr_autotrader.py
"""
import sys, time, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

import yfinance as yf
import pandas as pd
from datetime import datetime

from core.kis_trader import get_balance, get_price, buy_order, sell_order

# ── 파라미터 ─────────────────────────────────────────────────
CAPITAL_KR   = 2_400_000   # 한국장 배분 자본 (240만)
RISK_PER_TRADE = 0.01      # 거래당 리스크 1%
RR_RATIO     = 2.0
MAX_SL_PCT   = 0.015
MIN_SL_PCT   = 0.001
ZONE_EXPIRE  = 20
SCAN_INTERVAL = 60 * 15    # 15분마다 스캔

KR_TICKERS = {
    '005930': ('삼성전자',       '005930.KS'),
    '000660': ('SK하이닉스',     '000660.KS'),
    '009150': ('삼성전기',       '009150.KS'),
    '034020': ('두산에너빌리티', '034020.KS'),
    '008060': ('대덕전자',       '008060.KS'),
}

# 포지션 관리
positions = {}  # {ticker: {entry, sl, tp, qty, type}}


def _load_15m(yf_ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.download(yf_ticker, period='5d', interval='15m',
                         auto_adjust=True, progress=False, multi_level_index=False)
        if df is None or df.empty: return None
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except: return None


def _detect_signal(df: pd.DataFrame) -> dict | None:
    if len(df) < 30: return None
    zones = []
    # FVG
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG','formed_i':i,
                          'zone_high':lo0,'zone_low':hi2,'expire_i':i+ZONE_EXPIRE})
    # OB
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        imp = float(df['High'].iloc[i+1:i+3].max())
        if (imp - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB','formed_i':i,
                          'zone_high':float(b['High']),'zone_low':float(b['Low']),
                          'expire_i':i+ZONE_EXPIRE})

    last_i = len(df) - 1
    active = [z for z in zones if z['formed_i'] < last_i and z['expire_i'] > last_i]
    if not active: return None

    bar = df.iloc[last_i]
    lo, cl, op = float(bar['Low']), float(bar['Close']), float(bar['Open'])

    for z in reversed(sorted(active, key=lambda x: x['formed_i'])):
        zh, zl = z['zone_high'], z['zone_low']
        if lo <= zh and cl >= zl:
            entry = min(op, zh) if op <= zh else zh
            sl_pct = (entry - zl) / entry
            if not (MIN_SL_PCT <= sl_pct <= MAX_SL_PCT): continue
            return {
                'type': z['type'],
                'entry': round(entry),
                'sl': round(entry - entry * sl_pct),
                'tp': round(entry + entry * sl_pct * RR_RATIO),
                'sl_pct': sl_pct,
            }
    return None


def _is_market_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5: return False
    h, m = now.hour, now.minute
    return (9, 0) <= (h, m) <= (14, 30)


def _is_force_close() -> bool:
    now = datetime.now()
    h, m = now.hour, now.minute
    return (h, m) >= (14, 55)


def scan_and_trade():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f'\n[{now_str}] FVG+OB 스캔 시작')

    # 강제청산 시간
    if _is_force_close():
        for ticker, pos in list(positions.items()):
            price = get_price(ticker)
            r = sell_order(ticker, pos['qty'], 0)
            pnl_pct = (price - pos['entry']) / pos['entry'] * 100
            print(f'  [강제청산] {ticker} {pnl_pct:+.2f}% -> {r["msg"]}')
            del positions[ticker]
        return

    # 보유 포지션 TP/SL 체크
    for ticker, pos in list(positions.items()):
        price = get_price(ticker)
        if price <= 0: continue
        name = KR_TICKERS.get(ticker, (ticker,))[0]

        if price >= pos['tp']:
            r = sell_order(ticker, pos['qty'], pos['tp'])
            pnl_pct = (pos['tp'] - pos['entry']) / pos['entry'] * 100
            print(f'  [TP 도달] {name}({ticker}) +{pnl_pct:.2f}% -> {r["msg"]}')
            del positions[ticker]
        elif price <= pos['sl']:
            r = sell_order(ticker, pos['qty'], pos['sl'])
            pnl_pct = (pos['sl'] - pos['entry']) / pos['entry'] * 100
            print(f'  [SL 도달] {name}({ticker}) {pnl_pct:.2f}% -> {r["msg"]}')
            del positions[ticker]
        else:
            pnl_pct = (price - pos['entry']) / pos['entry'] * 100
            print(f'  [보유중] {name}({ticker}) 현재가={price:,} {pnl_pct:+.2f}%')

    if not _is_market_open():
        print(f'  장 외 시간 — 스캔 스킵')
        return

    # 신규 신호 스캔
    bal = get_balance()
    cash = bal.get('cash', 0)
    print(f'  예수금: {cash:,}원 | 보유포지션: {len(positions)}개')

    for ticker, (name, yf_tk) in KR_TICKERS.items():
        if ticker in positions: continue  # 이미 보유중

        df = _load_15m(yf_tk)
        if df is None: continue

        sig = _detect_signal(df)
        if not sig:
            print(f'  {name}({ticker}): 신호없음')
            continue

        # 포지션 크기 계산 (리스크 1%)
        risk_amt  = CAPITAL_KR * RISK_PER_TRADE
        sl_dist   = sig['entry'] - sig['sl']
        if sl_dist <= 0: continue
        qty = max(1, int(risk_amt / sl_dist))
        cost = sig['entry'] * qty

        if cost > cash * 0.4:  # 예수금 40% 초과 방지
            qty  = max(1, int(cash * 0.4 / sig['entry']))
            cost = sig['entry'] * qty

        print(f'  *** {name}({ticker}) [{sig["type"]}] 진입={sig["entry"]:,} '
              f'TP={sig["tp"]:,} SL={sig["sl"]:,} {qty}주 ({cost:,}원)')

        r = buy_order(ticker, qty, 0)  # 시장가 매수
        if r['success']:
            positions[ticker] = {
                'entry': sig['entry'], 'sl': sig['sl'],
                'tp': sig['tp'], 'qty': qty, 'type': sig['type'],
            }
            print(f'     -> 매수 완료 주문번호: {r["order_no"]}')
        else:
            print(f'     -> 매수 실패: {r["msg"]}')


def run():
    print('=' * 60)
    print('  Warren KR 자동매매 (모의투자) 시작')
    print(f'  배분자본: {CAPITAL_KR:,}원 | 리스크: {RISK_PER_TRADE*100:.0f}%/trade')
    print(f'  종목: {", ".join(v[0] for v in KR_TICKERS.values())}')
    print('  종료: Ctrl+C')
    print('=' * 60)

    # 초기 잔고 확인
    bal = get_balance()
    print(f'\n  예수금: {bal["cash"]:,}원 | 총평가: {bal["total"]:,}원')

    while True:
        try:
            scan_and_trade()
            next_scan = datetime.now().strftime('%H:%M')
            print(f'  다음 스캔: 15분 후')
            time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print('\n  봇 종료')
            break
        except Exception as e:
            print(f'  오류: {e}')
            time.sleep(60)


if __name__ == '__main__':
    run()
