# -*- coding: utf-8 -*-
"""
FVG + Order Block 포워드 테스터
백테스트와 동일한 로직으로 실시간 신호 감지
"""
import warnings; warnings.filterwarnings('ignore')
import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

# ── 파라미터 (백테스트와 동일) ────────────────────────────────
RR_RATIO    = 2.0
MAX_SL_PCT  = 0.015
MIN_SL_PCT  = 0.001
ZONE_EXPIRE = 20   # 봉 기준

KR_TICKERS = {
    '005930': ('삼성전자',       '005930.KS', '15m'),
    '000660': ('SK하이닉스',     '000660.KS', '15m'),
    '009150': ('삼성전기',       '009150.KS', '15m'),
    '034020': ('두산에너빌리티', '034020.KS', '15m'),
    '008060': ('대덕전자',       '008060.KS', '15m'),
}

US_TICKERS = {
    'NVDA': ('엔비디아',  'NVDA', '15m'),
    'PLTR': ('팔란티어',  'PLTR', '15m'),
    'AMD':  ('AMD',       'AMD',  '15m'),
    'TSLA': ('테슬라',    'TSLA', '15m'),
    'SOXX': ('반도체ETF', 'SOXX', '15m'),
}


def _load(yf_ticker: str, interval: str = '15m') -> pd.DataFrame | None:
    try:
        df = yf.download(yf_ticker, period='5d', interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception as e:
        return None


def _detect_fvg(df: pd.DataFrame) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG', 'formed_i':i,
                          'zone_high':lo0, 'zone_low':hi2,
                          'expire_i':i + ZONE_EXPIRE})
    return zones


def _detect_ob(df: pd.DataFrame) -> list:
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB', 'formed_i':i,
                          'zone_high':float(b['High']),
                          'zone_low':float(b['Low']),
                          'expire_i':i + ZONE_EXPIRE})
    return zones


def _check_signal(df: pd.DataFrame) -> dict | None:
    """
    최근 봉 기준으로 FVG/OB 되돌림 진입 신호 체크
    Returns: 신호 딕셔너리 or None
    """
    if len(df) < 30: return None

    all_zones = sorted(_detect_fvg(df) + _detect_ob(df),
                       key=lambda z: z['formed_i'])

    # 아직 유효한 구간만 (마지막 봉 기준)
    last_i = len(df) - 1
    active = [z for z in all_zones
              if z['formed_i'] < last_i and z['expire_i'] > last_i]

    if not active: return None

    bar = df.iloc[last_i]
    hi  = float(bar['High'])
    lo  = float(bar['Low'])
    cl  = float(bar['Close'])
    op  = float(bar['Open'])

    for z in reversed(active):   # 최신 구간 우선
        zh = z['zone_high']
        zl = z['zone_low']

        # 가격이 구간에 되돌아왔는지
        if lo <= zh and cl >= zl:
            entry  = min(op, zh) if op <= zh else zh
            sl_pct = (entry - zl) / entry
            if not (MIN_SL_PCT <= sl_pct <= MAX_SL_PCT):
                continue

            sl = entry - entry * sl_pct
            tp = entry + entry * sl_pct * RR_RATIO

            return {
                'type':      z['type'],
                'entry':     round(entry, 4),
                'sl':        round(sl, 4),
                'tp':        round(tp, 4),
                'sl_pct':    round(-sl_pct * 100, 2),
                'tp_pct':    round(sl_pct * RR_RATIO * 100, 2),
                'zone_high': zh,
                'zone_low':  zl,
                'formed_bar': z['formed_i'],
            }
    return None


def scan_all() -> list:
    """전 종목 FVG+OB 신호 스캔"""
    signals = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"\n{'='*65}")
    print(f"  FVG+OB Forward Scanner [{now_str}]")
    print(f"  KR 5종목 + US 5종목 (15분봉)")
    print(f"{'='*65}\n")

    # ── 한국주식 ────────────────────────────────────────────
    print("  [한국주식]")
    for code, (name, yf_tk, interval) in KR_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal(df)
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:,.0f} | 진입={sig['entry']:,.0f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker':code,'name':name,'market':'KR',
                            'price':price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:,.0f} | 신호없음")

    # ── 미국주식 ────────────────────────────────────────────
    print("\n  [미국주식]")
    for code, (name, yf_tk, interval) in US_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal(df)
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:.2f} | 진입={sig['entry']:.2f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker':code,'name':name,'market':'US',
                            'price':price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:.2f} | 신호없음")

    print(f"\n  {'='*40}")
    print(f"  총 신호: {len(signals)}건")
    for s in signals:
        print(f"  >>> {s['name']} | {s['type']} | "
              f"진입={s['entry']} TP=+{s['tp_pct']:.2f}% SL={s['sl_pct']:.2f}%")
    print(f"{'='*65}\n")

    return signals


if __name__ == '__main__':
    scan_all()
