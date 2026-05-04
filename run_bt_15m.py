# -*- coding: utf-8 -*-
"""
15분봉 FVG+OB 백테스트 -- 원본 전략 재검증
===========================================
- 직접 Yahoo Finance v8 API 호출 (yfinance 우회)
- 대상: KR5 / US5 / CRYPTO4 = 14종목
- 타임프레임: 15분봉 (60일)
- 전략: FVG + Order Block
- 필터: Vol_Spike + Body_In_Zone + Zone_Mid
- R:R 1:2 / SL 구조기반(0.5~3%) / 수수료 포함
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
import urllib.request
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SL_FLOOR    = 0.005
SL_CAP      = 0.030
RR          = 2.0
MAX_HOLD    = 8
ZONE_EXPIRE = 20

FEE = {
    'KR':     0.0023,
    'US':     0.005,
    'CRYPTO': 0.001,
}

TICKERS = {
    '005930.KS': ('삼성전자',    'KR'),
    '000660.KS': ('SK하이닉스', 'KR'),
    '009150.KS': ('삼성전기',   'KR'),
    '034020.KS': ('두산에너빌', 'KR'),
    '008060.KS': ('대덕전자',   'KR'),
    'NVDA':      ('엔비디아',   'US'),
    'PLTR':      ('팔란티어',   'US'),
    'AMD':       ('AMD',         'US'),
    'TSLA':      ('테슬라',     'US'),
    'SOXX':      ('반도체ETF',  'US'),
    'BTC-USD':   ('비트코인',   'CRYPTO'),
    'ETH-USD':   ('이더리움',   'CRYPTO'),
    'SOL-USD':   ('솔라나',     'CRYPTO'),
    'XRP-USD':   ('리플',       'CRYPTO'),
}


def fetch_15m(ticker):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval=15m&range=60d')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        r    = data.get('chart', {}).get('result', [])
        if not r:
            return None
        ts   = r[0]['timestamp']
        q    = r[0]['indicators']['quote'][0]
        df   = pd.DataFrame({
            'Open':   q['open'],
            'High':   q['high'],
            'Low':    q['low'],
            'Close':  q.get('close', []),
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        df = df.dropna()
        return df if len(df) >= 50 else None
    except Exception:
        return None


def detect_zones(df):
    zones = []
    n = len(df)
    for i in range(2, n):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / max(hi2, 1e-9) > 0.0005:
            zones.append({'type':'FVG','fi':i,'zh':lo0,'zl':hi2,'exp':i+ZONE_EXPIRE})
    for i in range(1, n-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']):
            continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / max(float(b['High']), 1e-9) > 0.003:
            zones.append({'type':'OB','fi':i,'zh':float(b['High']),'zl':float(b['Low']),'exp':i+ZONE_EXPIRE})
    return zones


def backtest(ticker, name, market, df):
    zones_all = detect_zones(df)
    fee       = FEE[market]
    trades    = []
    i         = 30

    while i < len(df) - 1:
        row = df.iloc[i]
        cl  = float(row['Close'])
        lo  = float(row['Low'])
        op  = float(row['Open'])

        active = [z for z in zones_all if z['fi'] < i < z['exp']]
        hit = None
        for z in reversed(active):
            if lo <= z['zh'] and cl >= z['zl']:
                hit = z
                break
        if not hit:
            i += 1
            continue

        vol_w = df['Volume'].iloc[max(0, i-20):i]
        avg_v = float(vol_w.mean()) if len(vol_w) > 0 else 0
        cur_v = float(df['Volume'].iloc[i]) if df['Volume'].iloc[i] else 0
        if not (avg_v > 0 and cur_v > avg_v * 1.5):
            i += 1
            continue

        body_low = min(cl, op)
        if not (body_low >= hit['zl'] * 0.998 and cl >= hit['zl']):
            i += 1
            continue

        zone_mid = hit['zl'] + (hit['zh'] - hit['zl']) * 0.5
        if cl < zone_mid:
            i += 1
            continue

        entry  = cl
        sl_pct = max(min((entry - hit['zl']) / max(entry, 1e-9), SL_CAP), SL_FLOOR)
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + sl_pct * RR)

        result    = 'HOLD'
        exit_p    = None
        hold_bars = MAX_HOLD

        for j in range(1, MAX_HOLD + 1):
            if i + j >= len(df):
                break
            fut = df.iloc[i + j]
            if float(fut['Low']) <= sl:
                result = 'LOSS'; exit_p = sl; hold_bars = j; break
            if float(fut['High']) >= tp:
                result = 'WIN';  exit_p = tp; hold_bars = j; break

        if result == 'HOLD':
            exit_p    = float(df.iloc[min(i+MAX_HOLD, len(df)-1)]['Close'])
            result    = 'WIN' if exit_p >= entry else 'LOSS'
            hold_bars = MAX_HOLD

        gross_pnl = (exit_p - entry) / entry
        net_pnl   = gross_pnl - fee

        trades.append({
            'result':    result,
            'gross_pnl': gross_pnl * 100,
            'net_pnl':   net_pnl * 100,
            'hold':      hold_bars,
            'sl_pct':    sl_pct * 100,
            'zone_type': hit['type'],
        })

        i += hold_bars + 1

    if not trades:
        return None

    n    = len(trades)
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    wr   = wins / n * 100

    net_ev    = np.mean([t['net_pnl'] for t in trades])
    gross_ev  = np.mean([t['gross_pnl'] for t in trades])
    net_total = sum(t['net_pnl'] for t in trades)
    avg_hold  = np.mean([t['hold'] for t in trades])
    avg_sl    = np.mean([t['sl_pct'] for t in trades])

    mth_trades = n / 2
    mth_ret    = mth_trades * net_ev

    wins_sum = sum(t['net_pnl'] for t in trades if t['result'] == 'WIN')
    loss_sum = abs(sum(t['net_pnl'] for t in trades if t['result'] == 'LOSS'))
    pf       = wins_sum / loss_sum if loss_sum > 0 else float('inf')

    return {
        'ticker': ticker, 'name': name, 'market': market,
        'n': n, 'wr': wr,
        'gross_ev': gross_ev, 'net_ev': net_ev,
        'net_total': net_total, 'avg_hold': avg_hold,
        'avg_sl': avg_sl, 'pf': pf,
        'mth_trades': mth_trades, 'mth_ret': mth_ret,
    }


def main():
    print('=' * 70)
    print(f'  15분봉 FVG+OB 백테스트 [{datetime.now().strftime("%Y-%m-%d %H:%M")}]')
    print('  FVG/OB 0.05% | Vol_Spike+Body_In_Zone+ZoneMid | R:R 1:2')
    print('  SL 존기반(0.5~3%) | 수수료: KR 0.23% / US 0.5% / CRYPTO 0.1%')
    print('=' * 70)

    all_results = []

    for ticker, (name, market) in TICKERS.items():
        print(f'  {name}({ticker})...', end='', flush=True)
        df = fetch_15m(ticker)

        if df is None:
            print(' 데이터없음')
            continue

        print(f' {len(df)}봉', end='', flush=True)
        r = backtest(ticker, name, market, df)

        if r is None:
            print(' 신호없음')
            continue

        if r['wr'] >= 55 and r['net_ev'] > 0:
            flag = ' ★'
        elif r['wr'] >= 45 and r['net_ev'] > 0:
            flag = ' ▲'
        else:
            flag = '  '

        print(f'\n   {flag} {r["n"]:3d}건 | WR={r["wr"]:5.1f}% | '
              f'순EV={r["net_ev"]:+.3f}% | 총수익={r["net_total"]:+.1f}% | '
              f'PF={r["pf"]:.2f} | SL평균={r["avg_sl"]:.2f}% | 보유={r["avg_hold"]:.1f}봉')
        all_results.append(r)

    print()
    print('=' * 70)
    print('  종목별 성과 요약 (순EV 순)')
    print('=' * 70)
    print(f'  {"종목":<12} {"시장":<8} {"건수":<6} {"WR%":<8} {"순EV%":<10} '
          f'{"PF":<6} {"월수익%":<10} 판정')
    print('  ' + '-' * 65)

    for r in sorted(all_results, key=lambda x: -x['net_ev']):
        ok = r['wr'] >= 55 and r['net_ev'] > 0
        borderline = r['wr'] >= 45 and r['net_ev'] > 0
        flag = '★ 채택' if ok else ('▲ 검토' if borderline else '  제외')
        print(f'  {r["name"]:<12} {r["market"]:<8} {r["n"]:4d}건  '
              f'{r["wr"]:5.1f}%   {r["net_ev"]:+.3f}%     '
              f'{r["pf"]:4.2f}   {r["mth_ret"]:+.2f}%/월  {flag}')

    viable = [r for r in all_results if r['wr'] >= 45 and r['net_ev'] > 0]

    print()
    print('=' * 70)
    print('  수익 시뮬레이션 (KR 1,000만 / US 1,000만 / CRYPTO 500만)')
    print('=' * 70)

    SEED = {'KR': 1e7, 'US': 1e7, 'CRYPTO': 5e6}
    total_won = 0.0

    for mkt in ['KR', 'US', 'CRYPTO']:
        grp = [r for r in viable if r['market'] == mkt]
        if not grp:
            print(f'  [{mkt}] 채택 종목 없음')
            continue
        seed   = SEED[mkt]
        n_coin = len(grp)
        alloc  = seed / n_coin
        mth_won = sum(r['mth_ret'] / 100 * alloc for r in grp)
        mth_pct = mth_won / seed * 100
        names   = ', '.join(r['name'] for r in grp)
        print(f'  [{mkt}] {n_coin}종목 ({names})')
        print(f'    시드 {seed/1e4:,.0f}만원 | 종목당 {alloc/1e4:.1f}만원')
        print(f'    월수익: {mth_won/1e4:,.1f}만원 ({mth_pct:.2f}%/월)')
        total_won += mth_won

    total_seed = sum(SEED.values())
    total_pct  = total_won / total_seed * 100 if total_seed > 0 else 0
    print()
    print('=' * 70)
    print(f'  합계 시드 {total_seed/1e4:,.0f}만원 | 월수익 {total_won/1e4:,.1f}만원 ({total_pct:.2f}%/월)')
    print(f'  연간 환산 APY: {total_pct*12:.1f}%')
    print('=' * 70)


if __name__ == '__main__':
    main()
