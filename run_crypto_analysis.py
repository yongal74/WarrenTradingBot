# -*- coding: utf-8 -*-
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, urllib.request

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SL_FLOOR = 0.005; SL_CAP = 0.030; RR = 3.0; FEE = 0.001; MAX_HOLD = 90

TICKERS_4H = {
    'BTC-USD':  '비트코인',
    'ETH-USD':  '이더리움',
    'SOL-USD':  '솔라나',
    'XRP-USD':  '리플',
    'BNB-USD':  'BNB',
    'DOGE-USD': '도지코인',
    'ADA-USD':  '에이다',
    'AVAX-USD': '아발란체',
    'LINK-USD': '체인링크',
    'LTC-USD':  '라이트코인',
}

def fetch(ticker, interval='1h', range_='2y'):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval={interval}&range={range_}')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        r    = data.get('chart', {}).get('result', [])
        if not r: return None
        ts   = r[0]['timestamp']
        q    = r[0]['indicators']['quote'][0]
        df   = pd.DataFrame({
            'Open':   q['open'],   'High': q['high'],
            'Low':    q['low'],    'Close': q.get('close', []),
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except:
        return None

def resample_4h(df):
    return df.resample('4h').agg(
        {'Open': 'first', 'High': 'max', 'Low': 'min',
         'Close': 'last', 'Volume': 'sum'}
    ).dropna()

def detect_zones(df):
    zones = []
    for i in range(2, len(df)-1):
        if float(df['Low'].iloc[i]) > float(df['High'].iloc[i-2]):
            zh = float(df['Low'].iloc[i])
            zl = float(df['High'].iloc[i-2])
            if (zh - zl) / max(zl, 1e-9) > 0.002:
                zones.append({'type': 'FVG', 'fi': i, 'zh': zh, 'zl': zl,
                               'exp': i+30, 'touches': 0})
        if i >= 1:
            b = df.iloc[i-1]
            if float(b['Close']) < float(b['Open']):
                nxt = float(df['High'].iloc[i])
                if (nxt - float(b['High'])) / max(float(b['High']), 1e-9) > 0.003:
                    zones.append({'type': 'OB', 'fi': i-1,
                                  'zh': float(b['High']), 'zl': float(b['Low']),
                                  'exp': i+30, 'touches': 0})
    return zones

def backtest(ticker, name, df4h, extra_filters=False):
    zones_all = detect_zones(df4h)
    ema200 = df4h['Close'].ewm(span=200, adjust=False).mean()
    d      = df4h['Close'].diff()
    g      = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l      = (-d.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rsi14  = 100 - 100 / (1 + g / l.replace(0, np.nan))

    trades = []; i = 200
    while i < len(df4h) - 1:
        row = df4h.iloc[i]
        cl  = float(row['Close'])
        lo  = float(row['Low'])

        active = [z for z in zones_all if z['fi'] < i < z['exp']]
        hit = None
        for z in reversed(active):
            if lo <= z['zh'] and cl >= z['zl']:
                hit = z; break
        if not hit: i += 1; continue

        vol   = df4h['Volume'].iloc[max(0, i-20):i]
        avg_v = vol.mean()
        cur_v = float(df4h['Volume'].iloc[i]) if df4h['Volume'].iloc[i] else 0
        vs    = (avg_v > 0 and cur_v > avg_v * 1.5)
        op    = float(row['Open'])
        biz   = (min(cl, op) >= hit['zl'] * 0.998 and cl >= hit['zl'])
        if not (vs and biz): i += 1; continue

        zone_mid = hit['zl'] + (hit['zh'] - hit['zl']) * 0.5
        if cl < zone_mid: i += 1; continue

        if extra_filters:
            if cl < float(ema200.iloc[i]) * 0.97: i += 1; continue
            rsi_val = float(rsi14.iloc[i]) if not pd.isna(rsi14.iloc[i]) else 50
            if rsi_val > 55: i += 1; continue
            if hit['touches'] >= 2: i += 1; continue

        hit['touches'] += 1

        entry  = cl
        sl_pct = max(min((entry - hit['zl']) / entry, SL_CAP), SL_FLOOR)
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + sl_pct * RR)

        result = 'HOLD'; exit_p = None
        for j in range(1, MAX_HOLD+1):
            if i+j >= len(df4h): break
            fut = df4h.iloc[i+j]
            if float(fut['Low']) <= sl:   result='LOSS'; exit_p=sl; break
            if float(fut['High']) >= tp:  result='WIN';  exit_p=tp; break
        if result == 'HOLD':
            exit_p = float(df4h.iloc[min(i+MAX_HOLD, len(df4h)-1)]['Close'])
            result = 'WIN' if exit_p >= entry else 'LOSS'

        pnl = (exit_p - entry) / entry - FEE
        trades.append({'result': result, 'pnl': pnl * 100})
        i += MAX_HOLD

    if not trades: return None
    n    = len(trades)
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    wr   = wins / n * 100
    ev   = np.mean([t['pnl'] for t in trades])
    pnl_total = sum(t['pnl'] for t in trades)
    return {'ticker': ticker, 'name': name, 'n': n, 'wr': wr,
            'ev': ev, 'pnl': pnl_total, 'mth_n': n/24, 'mth_r': n/24*ev}


print('=' * 65)
print('  [Option 1+2] CRYPTO 4H 유니버스 확대 + 신호 품질 강화')
print('  기본: Vol_Spike+Body_In_Zone | 강화: +EMA200+RSI<55+FreshZone')
print('  R:R 1:3 | SL zone기반(0.5~3%) | 수수료 0.10%')
print('=' * 65)

base_results  = []
extra_results = []

for ticker, name in TICKERS_4H.items():
    print(f'  {name}({ticker})...', end='', flush=True)
    df1h = fetch(ticker, '1h', '2y')
    if df1h is None or len(df1h) < 500:
        print(' 데이터부족'); continue
    df4h = resample_4h(df1h)
    if len(df4h) < 250:
        print(' 4H부족'); continue

    r_base  = backtest(ticker, name, df4h.copy(), extra_filters=False)
    r_extra = backtest(ticker, name, df4h.copy(), extra_filters=True)

    if r_base:
        flag = '★' if r_base['wr'] >= 55 and r_base['ev'] > 0 else ' '
        print(f' {flag} {r_base["n"]}건 WR={r_base["wr"]:.1f}% '
              f'EV={r_base["ev"]:+.3f}% PnL={r_base["pnl"]:+.1f}%')
        base_results.append(r_base)
        if r_extra:
            extra_results.append(r_extra)
    else:
        print(' 신호없음')

print()
print('=' * 65)
print('  [Option 2] 추가 필터 효과 비교')
print('=' * 65)
print(f'  {"종목":<12} {"기본WR":<9} {"기본EV":<10} {"강화WR":<9} {"강화EV":<10} 변화')
print(f'  {"-"*58}')
for b in base_results:
    e = next((x for x in extra_results if x['ticker'] == b['ticker']), None)
    if e:
        dwr = e['wr'] - b['wr']
        dev = e['ev'] - b['ev']
        arrow = '↑' if dwr > 0 else '↓'
        print(f'  {b["name"]:<12} {b["wr"]:5.1f}%   {b["ev"]:+.3f}%     '
              f'{e["wr"]:5.1f}%   {e["ev"]:+.3f}%     '
              f'{arrow}{abs(dwr):.1f}%p / {dev:+.3f}%')

# 최적 유니버스: 기본 필터 기준 WR>=50 & EV>0
top6 = sorted([r for r in base_results if r['wr'] >= 50 and r['ev'] > 0],
              key=lambda x: -x['mth_r'])[:6]

print()
print('=' * 65)
print('  [Option 1] 최종 편입 유니버스 (WR>=50%, EV>0)')
print('=' * 65)
print(f'  {"종목":<12} {"건수/월":<8} {"EV/trade":<12} {"월수익률":<10} 판정')
print(f'  {"-"*52}')
for r in sorted(base_results, key=lambda x: -x['mth_r']):
    ok = r['wr'] >= 50 and r['ev'] > 0
    flag = '★ 편입' if ok else '  제외'
    print(f'  {r["name"]:<12} {r["mth_n"]:5.1f}건    {r["ev"]:+.3f}%       '
          f'{r["mth_r"]:+.3f}%/월    {flag}')

print()
print('=' * 65)
print('  [Option 3] 복리 시뮬레이션 (2.5억 / 수익 재투자)')
print('=' * 65)

n_coins   = len(top6)
seed      = 2.5e8

if n_coins > 0:
    avg_mth_pct = np.mean([r['mth_r'] for r in top6]) / 100
    print(f'  편입 종목 {n_coins}개: {[r["name"] for r in top6]}')
    print(f'  종목별 평균 월수익률: {avg_mth_pct*100:.2f}%')
    print(f'  전체 월수익률 (포트폴리오): {avg_mth_pct*100*n_coins/n_coins:.2f}% → '
          f'종목 균등배분 기준')
    print()

    # 각 종목에 1/n_coins씩 배분
    portfolio_mth = avg_mth_pct  # 균등 배분 시 포트폴리오 전체 수익률 = 평균
    print(f'  {"월":<5} {"시드":<14} {"월수익":<12} {"누적수익":<14} 비고')
    print(f'  {"-"*55}')
    capital = seed; cum = 0
    for m in range(1, 13):
        monthly = capital * portfolio_mth * n_coins / n_coins
        # 전체 자본에서 n_coins 종목 균등 배분 운용
        monthly_total = capital * avg_mth_pct
        capital += monthly_total; cum += monthly_total
        note = ''
        if monthly_total >= 1.5e7: note = ' ★ 월1500만 달성'
        elif monthly_total >= 1.0e7: note = ' ← 월1000만'
        elif monthly_total >= 0.7e7: note = ' ← 월700만'
        if m <= 8 or monthly_total >= 5e6:
            print(f'  {m}월    {capital/1e8:.3f}억      {monthly_total/1e4:,.0f}만원       '
                  f'+{cum/1e4:,.0f}만원{note}')
    print()
    print(f'  12개월 후 시드: {capital/1e8:.2f}억')
    print(f'  12개월 누적수익: {cum/1e4:,.0f}만원')
else:
    print('  편입 가능 종목 없음 — 조건 완화 필요')
