# -*- coding: utf-8 -*-
"""
히스토리 리플레이 — V4_RELAXED 조건으로 과거 90일 day-by-day 시뮬레이션
=======================================================================
목적: 포워드테스팅 케이스 부족 문제 해결
  - 실시간 신호 대기 대신 과거 데이터로 즉시 케이스 생성
  - V4 완화조건 (RSI<70, MA20이하, EMA200위, FVG/OB) 적용
  - 결과는 REPLAY 태그로 실제 포워드와 구분
  - paper_trades.csv에 추가하지 않음 → 별도 replay_trades.csv 저장

실행: python -X utf8 run_history_replay.py
"""
import sys, json, csv
import pandas as pd
import numpy as np
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

OUT_FILE = LOG_DIR / 'replay_trades.csv'

# ── V4 완화 파라미터 ──────────────────────────────────────────
RSI_THRESH   = 70
USE_MA20     = True      # BB1하단 대신 MA20이하
MIN_QUALITY  = 3
SL_FLOOR     = 0.02
SL_CAP       = 0.08
MAX_HOLD     = 15        # 최대 보유일
REPLAY_DAYS  = 252       # 과거 1년치 (거래일 기준)

# ── 유니버스 (V4 확정) ────────────────────────────────────────
UNIVERSE = {
    # KR 스윙
    '005930.KS': ('삼성전자',   'KR', 2.0, 0.0023),
    '005380.KS': ('현대차',     'KR', 2.0, 0.0023),
    '000270.KS': ('기아',       'KR', 2.0, 0.0023),
    '008060.KS': ('대덕전자',   'KR', 2.0, 0.0023),
    '105560.KS': ('KB금융',     'KR', 2.0, 0.0023),
    '000660.KS': ('SK하이닉스', 'KR', 2.0, 0.0023),
    '009150.KS': ('삼성전기',   'KR', 2.0, 0.0023),
    '051910.KS': ('LG화학',     'KR', 2.0, 0.0023),
    # US 스윙
    'SOXX':  ('반도체ETF',  'US', 2.0, 0.005),
    'PLTR':  ('팔란티어',   'US', 2.0, 0.005),
    'RTX':   ('RTX',        'US', 2.0, 0.005),
    'GOOGL': ('구글',       'US', 2.0, 0.005),
    'AMZN':  ('아마존',     'US', 2.0, 0.005),
    'META':  ('메타',       'US', 2.0, 0.005),
    'HESAY': ('에르메스',   'US', 2.0, 0.005),
    'NVDA':  ('엔비디아',   'US', 2.0, 0.005),
    'QQQI':  ('QQQI',       'US', 2.0, 0.005),
    'MSFT':  ('MSFT',       'US', 2.0, 0.005),
    # CRYPTO 4H → 일봉 리플레이
    'BTC-USD':  ('비트코인', 'CRYPTO', 3.0, 0.001),
    'ETH-USD':  ('이더리움', 'CRYPTO', 3.0, 0.001),
    'SOL-USD':  ('솔라나',   'CRYPTO', 3.0, 0.001),
    'XRP-USD':  ('리플',     'CRYPTO', 3.0, 0.001),
    'BNB-USD':  ('BNB',      'CRYPTO', 3.0, 0.001),
    'DOGE-USD': ('도지코인', 'CRYPTO', 3.0, 0.001),
}


def _fetch(ticker: str) -> pd.DataFrame | None:
    # 2y 데이터 필요: EMA200(200봉) + 1년 리플레이(252봉)
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval=1d&range=2y')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        r    = data.get('chart', {}).get('result', [])
        if not r: return None
        ts   = r[0]['timestamp']
        q    = r[0]['indicators']['quote'][0]
        adj  = r[0]['indicators'].get('adjclose', [])
        closes = (adj[0]['adjclose'] if adj and isinstance(adj[0], dict) and adj[0].get('adjclose')
                  else q.get('close', []))
        df = pd.DataFrame({
            'Open': q['open'], 'High': q['high'],
            'Low':  q['low'],  'Close': closes,
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except Exception as e:
        return None


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df['Close']
    df['ema200'] = c.ewm(span=200, adjust=False).mean()
    ma20 = c.rolling(20).mean()
    sd20 = c.rolling(20).std()
    df['ma20']   = ma20
    df['bb1_lo'] = ma20 - sd20
    d = c.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    df['rsi'] = 100 - 100 / (1 + g / l.replace(0, float('nan')))
    # FVG (불리시: i-2 고가 < i 저가)
    df['fvg'] = (df['Low'] > df['High'].shift(2)) & (c > c.shift(1))
    # OB (하락봉 후 급등)
    df['ob']  = (c.shift(1) < c.shift(2)) & (c > c.shift(1)) & (c > ma20)
    return df


def _detect_zones(df: pd.DataFrame, up_to_i: int) -> list:
    zones = []
    sub = df.iloc[:up_to_i]
    # FVG zones
    for i in range(2, len(sub)):
        hi2 = float(sub['High'].iloc[i-2])
        lo0 = float(sub['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.003:
            zones.append({'type':'FVG','formed_i':i,'zone_high':lo0,'zone_low':hi2,'expire_i':i+30})
    # OB zones
    for i in range(1, len(sub)-2):
        b = sub.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        imp = float(sub['High'].iloc[i+1:min(i+3,len(sub))].max()) if i+1 < len(sub) else 0
        if imp and (imp - float(b['High'])) / float(b['High']) > 0.005:
            zones.append({'type':'OB','formed_i':i,'zone_high':float(b['High']),'zone_low':float(b['Low']),'expire_i':i+30})
    return zones


def replay_ticker(ticker: str, name: str, market: str,
                  rr: float, fee: float, df: pd.DataFrame) -> list:
    df = _add_indicators(df)
    trades = []
    cutoff = len(df) - REPLAY_DAYS

    i = max(200, cutoff)
    while i < len(df) - 1:
        row   = df.iloc[i]
        cl    = float(row['Close'])
        ema200= float(row['ema200'])
        ma20  = float(row['ma20'])
        rsi   = float(row['rsi'])
        date  = df.index[i].strftime('%Y-%m-%d')

        if any(pd.isna(x) for x in [ema200, ma20, rsi]):
            i += 1; continue

        # V4 조건
        if cl < ema200 * 0.98:   i += 1; continue
        if cl > ma20:             i += 1; continue
        if rsi >= RSI_THRESH:     i += 1; continue

        # FVG/OB 존 체크
        zones  = _detect_zones(df, i)
        active = [z for z in zones if z['formed_i'] < i and z['expire_i'] > i]
        lo     = float(row['Low'])
        hit_zone = None
        for z in reversed(active):
            if lo <= z['zone_high'] and cl >= z['zone_low']:
                hit_zone = z; break
        if not hit_zone:
            i += 1; continue

        # 진입 확정
        zl     = hit_zone['zone_low']
        sl_pct = max(min((cl - zl) / cl if cl > 0 else SL_FLOOR, SL_CAP), SL_FLOOR)
        tp_pct = sl_pct * rr
        entry  = cl
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + tp_pct)

        # 결과 탐색
        result = 'HOLD'; exit_p = None; hold = 0
        for j in range(1, MAX_HOLD + 1):
            if i + j >= len(df): break
            fut = df.iloc[i + j]
            hold = j
            if float(fut['Low']) <= sl:
                result = 'LOSS'; exit_p = sl; break
            if float(fut['High']) >= tp:
                result = 'WIN';  exit_p = tp; break
        if result == 'HOLD':
            exit_p = float(df.iloc[min(i+MAX_HOLD, len(df)-1)]['Close'])
            result = 'WIN' if exit_p >= entry else 'LOSS'

        pnl_pct = (exit_p - entry) / entry - fee
        exit_date = df.index[min(i+hold, len(df)-1)].strftime('%Y-%m-%d')

        trades.append({
            'source':      'REPLAY',
            'ticker':      ticker,
            'name':        name,
            'market':      market,
            'entry_date':  date,
            'exit_date':   exit_date,
            'entry':       round(entry, 4),
            'exit':        round(exit_p, 4),
            'sl':          round(sl, 4),
            'tp':          round(tp, 4),
            'zone_type':   hit_zone['type'],
            'rsi':         round(rsi, 1),
            'result':      result,
            'pnl_pct':     round(pnl_pct * 100, 3),
            'hold_days':   hold,
            'rr':          rr,
            'condition':   f'V4_RSI{RSI_THRESH}_MA20_RR{rr}',
        })
        i += MAX_HOLD  # 다음 탐색

    return trades


def main():
    print(f'\n{"="*65}')
    print(f'  히스토리 리플레이 — V4_RELAXED 조건 / 과거 {REPLAY_DAYS}일')
    print(f'  조건: EMA200위 + MA20이하 + RSI<{RSI_THRESH} + FVG/OB존')
    print(f'{"="*65}\n')

    all_trades = []
    stats = {}

    for ticker, (name, market, rr, fee) in UNIVERSE.items():
        df = _fetch(ticker)
        if df is None or len(df) < 210:
            print(f'  {name:15s} — 데이터 부족 ({len(df) if df is not None else 0}행)')
            continue
        trades = replay_ticker(ticker, name, market, rr, fee, df)
        n    = len(trades)
        wins = sum(1 for t in trades if t['result'] == 'WIN')
        wr   = wins/n*100 if n else 0
        ev   = np.mean([t['pnl_pct'] for t in trades]) if trades else 0
        flag = '★' if wr >= 60 and ev > 0 else ' '
        print(f'  {flag}{name:15s} [{market:6s}] {n:3d}건 | WR={wr:5.1f}% | EV={ev:+.2f}%')
        all_trades.extend(trades)
        stats[ticker] = {'name':name,'market':market,'n':n,'wr':wr,'ev':ev}

    # ── 전체 통계 ──────────────────────────────────────────────
    total = len(all_trades)
    wins  = sum(1 for t in all_trades if t['result'] == 'WIN')
    wr    = wins/total*100 if total else 0
    ev    = np.mean([t['pnl_pct'] for t in all_trades]) if all_trades else 0

    print(f'\n{"="*65}')
    print(f'  전체 결과: {total}건 | WR={wr:.1f}% | EV={ev:+.2f}%/trade')

    # 시장별 집계
    for mkt in ['KR','US','CRYPTO']:
        mt = [t for t in all_trades if t['market']==mkt]
        if mt:
            mw = sum(1 for t in mt if t['result']=='WIN')
            print(f'  {mkt:6s}: {len(mt):3d}건 | WR={mw/len(mt)*100:.1f}% | EV={np.mean([t["pnl_pct"] for t in mt]):+.2f}%')

    # ── CSV 저장 ────────────────────────────────────────────────
    if all_trades:
        keys = all_trades[0].keys()
        with open(OUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(all_trades)
        print(f'\n  저장: {OUT_FILE.name} ({total}건)')

    print(f'\n  [참고] REPLAY 케이스는 실제 포워드와 구분됨')
    print(f'  [다음] 케이스 축적 후 V3(원본) vs V4(완화) WR 비교 예정')
    print(f'{"="*65}\n')

    return all_trades


if __name__ == '__main__':
    main()
