# -*- coding: utf-8 -*-
"""
Warren V5 백테스트 — A+B+C 통합
================================================
A) US 수수료 0.25%로 현실화 (기존 0.5%)
B) KR 종목 15개로 확대 (기존 5개)
C) CRYPTO 4H 타임프레임 전환 (기존 15m)
------------------------------------------------
KR 15분봉 | US 15분봉 | CRYPTO 4H (1H resample)
R:R 1:2 (KR/US) | R:R 1:3 (CRYPTO 4H)
백테스팅 기간: KR/US 60일, CRYPTO 2년
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
import urllib.request
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 파라미터 ──────────────────────────────────────────────────────
SL_FLOOR    = 0.005
SL_CAP      = 0.030
ZONE_EXPIRE = 20

# 타임프레임별 설정
CFG = {
    'KR_15m':     {'rr': 2.0, 'max_hold': 8,  'fee': 0.0023},
    'US_15m':     {'rr': 2.0, 'max_hold': 8,  'fee': 0.0025},  # A) 0.5% -> 0.25%
    'CRYPTO_4H':  {'rr': 3.0, 'max_hold': 90, 'fee': 0.001},   # C) 4H
}

# B) KR 15종목으로 확대
KR_TICKERS = {
    '005930.KS': '삼성전자',
    '000660.KS': 'SK하이닉스',
    '009150.KS': '삼성전기',
    '034020.KS': '두산에너빌',
    '008060.KS': '대덕전자',
    '005380.KS': '현대차',
    '000270.KS': '기아',
    '035420.KS': 'NAVER',
    '051910.KS': 'LG화학',
    '068270.KS': '셀트리온',
    '035720.KS': '카카오',
    '066570.KS': 'LG전자',
    '096770.KS': 'SK이노베이션',
    '028260.KS': '삼성물산',
    '017670.KS': 'SK텔레콤',
}

US_TICKERS = {
    'NVDA':  '엔비디아',
    'PLTR':  '팔란티어',
    'AMD':   'AMD',
    'TSLA':  '테슬라',
    'SOXX':  '반도체ETF',
}

CRYPTO_TICKERS = {
    'BTC-USD':  '비트코인',
    'ETH-USD':  '이더리움',
    'SOL-USD':  '솔라나',
    'XRP-USD':  '리플',
    'BNB-USD':  'BNB',
    'DOGE-USD': '도지코인',
}


def fetch(ticker, interval, range_):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval={interval}&range={range_}')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        r    = data.get('chart', {}).get('result', [])
        if not r:
            return None
        ts = r[0]['timestamp']
        q  = r[0]['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open':   q['open'],
            'High':   q['high'],
            'Low':    q['low'],
            'Close':  q.get('close', []),
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except Exception:
        return None


def resample_4h(df):
    return df.resample('4h').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    ).dropna()


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


def backtest_core(df, cfg_key, warmup=30):
    cfg       = CFG[cfg_key]
    rr        = cfg['rr']
    max_hold  = cfg['max_hold']
    fee       = cfg['fee']
    zones_all = detect_zones(df)
    trades    = []
    i         = warmup

    while i < len(df) - 1:
        row = df.iloc[i]
        cl  = float(row['Close'])
        lo  = float(row['Low'])
        op  = float(row['Open'])

        active = [z for z in zones_all if z['fi'] < i < z['exp']]
        hit = None
        for z in reversed(active):
            if lo <= z['zh'] and cl >= z['zl']:
                hit = z; break
        if not hit:
            i += 1; continue

        vol_w = df['Volume'].iloc[max(0, i-20):i]
        avg_v = float(vol_w.mean()) if len(vol_w) > 0 else 0
        cur_v = float(df['Volume'].iloc[i]) if df['Volume'].iloc[i] else 0
        if not (avg_v > 0 and cur_v > avg_v * 1.5):
            i += 1; continue

        body_low = min(cl, op)
        if not (body_low >= hit['zl'] * 0.998 and cl >= hit['zl']):
            i += 1; continue

        zone_mid = hit['zl'] + (hit['zh'] - hit['zl']) * 0.5
        if cl < zone_mid:
            i += 1; continue

        entry  = cl
        sl_pct = max(min((entry - hit['zl']) / max(entry, 1e-9), SL_CAP), SL_FLOOR)
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + sl_pct * rr)

        result = 'HOLD'; exit_p = None; hold_bars = max_hold
        for j in range(1, max_hold + 1):
            if i + j >= len(df): break
            fut = df.iloc[i + j]
            if float(fut['Low']) <= sl:
                result = 'LOSS'; exit_p = sl; hold_bars = j; break
            if float(fut['High']) >= tp:
                result = 'WIN';  exit_p = tp; hold_bars = j; break

        if result == 'HOLD':
            exit_p    = float(df.iloc[min(i+max_hold, len(df)-1)]['Close'])
            result    = 'WIN' if exit_p >= entry else 'LOSS'
            hold_bars = max_hold

        gross = (exit_p - entry) / entry
        net   = gross - fee
        trades.append({'result': result, 'gross': gross*100, 'net': net*100, 'hold': hold_bars})
        i += hold_bars + 1

    return trades


def summarize(ticker, name, market, trades, period_months):
    if not trades:
        return None
    n    = len(trades)
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    wr   = wins / n * 100
    net_ev    = np.mean([t['net'] for t in trades])
    gross_ev  = np.mean([t['gross'] for t in trades])
    net_total = sum(t['net'] for t in trades)
    avg_hold  = np.mean([t['hold'] for t in trades])
    wins_sum  = sum(t['net'] for t in trades if t['result'] == 'WIN')
    loss_sum  = abs(sum(t['net'] for t in trades if t['result'] == 'LOSS'))
    pf        = wins_sum / loss_sum if loss_sum > 0 else float('inf')
    mth_n     = n / period_months
    mth_ret   = mth_n * net_ev
    return {
        'ticker': ticker, 'name': name, 'market': market,
        'n': n, 'wr': wr, 'net_ev': net_ev, 'gross_ev': gross_ev,
        'net_total': net_total, 'avg_hold': avg_hold, 'pf': pf,
        'mth_n': mth_n, 'mth_ret': mth_ret,
        'period_months': period_months,
    }


def print_result(r):
    if r['wr'] >= 55 and r['net_ev'] > 0:
        flag = ' ★'
    elif r['wr'] >= 45 and r['net_ev'] > 0:
        flag = ' ▲'
    else:
        flag = '  '
    print(f'   {flag} {r["n"]:3d}건 | WR={r["wr"]:5.1f}% | '
          f'순EV={r["net_ev"]:+.3f}% | 총={r["net_total"]:+.1f}% | '
          f'PF={r["pf"]:.2f} | {r["avg_hold"]:.1f}봉')


def main():
    print('=' * 72)
    print(f'  Warren V5 백테스트 [{datetime.now().strftime("%Y-%m-%d %H:%M")}]')
    print('  A) US 수수료 0.25% | B) KR 15종목 | C) CRYPTO 4H R:R 1:3')
    print('  KR/US: 60일 15분봉 | CRYPTO: 2년 4H봉')
    print('=' * 72)

    all_results = []

    # ── KR 15종목 15분봉 ─────────────────────────────────────────
    print('\n[KR] 15종목 15분봉 (60일, 수수료 0.23%)')
    print('-' * 60)
    for ticker, name in KR_TICKERS.items():
        print(f'  {name}({ticker})...', end='', flush=True)
        df = fetch(ticker, '15m', '60d')
        if df is None or len(df) < 50:
            print(' 데이터없음'); continue
        print(f' {len(df)}봉', end='')
        trades = backtest_core(df, 'KR_15m')
        r = summarize(ticker, name, 'KR', trades, 2.0)
        if r:
            print_result(r)
            all_results.append(r)
        else:
            print(' 신호없음')

    # ── US 5종목 15분봉 ──────────────────────────────────────────
    print('\n[US] 5종목 15분봉 (60일, 수수료 0.25% ← A 수정)')
    print('-' * 60)
    for ticker, name in US_TICKERS.items():
        print(f'  {name}({ticker})...', end='', flush=True)
        df = fetch(ticker, '15m', '60d')
        if df is None or len(df) < 50:
            print(' 데이터없음'); continue
        print(f' {len(df)}봉', end='')
        trades = backtest_core(df, 'US_15m')
        r = summarize(ticker, name, 'US', trades, 2.0)
        if r:
            print_result(r)
            all_results.append(r)
        else:
            print(' 신호없음')

    # ── CRYPTO 6종목 4H ─────────────────────────────────────────
    print('\n[CRYPTO] 6종목 4H봉 (2년, 수수료 0.10% ← C 타임프레임 전환)')
    print('-' * 60)
    for ticker, name in CRYPTO_TICKERS.items():
        print(f'  {name}({ticker})...', end='', flush=True)
        df1h = fetch(ticker, '1h', '2y')
        if df1h is None or len(df1h) < 500:
            print(' 데이터없음'); continue
        df = resample_4h(df1h)
        print(f' 4H={len(df)}봉', end='')
        trades = backtest_core(df, 'CRYPTO_4H', warmup=50)
        r = summarize(ticker, name, 'CRYPTO', trades, 24.0)
        if r:
            print_result(r)
            all_results.append(r)
        else:
            print(' 신호없음')

    # ── 요약 테이블 ──────────────────────────────────────────────
    print()
    print('=' * 72)
    print('  V5 전체 요약 (순EV 기준 정렬)')
    print('=' * 72)
    print(f'  {"종목":<12} {"시장":<8} {"TF":<6} {"건수":<6} {"WR%":<8} '
          f'{"순EV%":<10} {"PF":<6} {"월수익%":<10} 판정')
    print('  ' + '-' * 68)

    tf_map = {'KR': '15m', 'US': '15m', 'CRYPTO': '4H'}
    for r in sorted(all_results, key=lambda x: -x['net_ev']):
        ok = r['wr'] >= 55 and r['net_ev'] > 0
        borderline = r['wr'] >= 45 and r['net_ev'] > 0
        flag = '★ 채택' if ok else ('▲ 검토' if borderline else '  제외')
        tf = tf_map[r['market']]
        print(f'  {r["name"]:<12} {r["market"]:<8} {tf:<6} {r["n"]:4d}건  '
              f'{r["wr"]:5.1f}%   {r["net_ev"]:+.3f}%     '
              f'{r["pf"]:4.2f}   {r["mth_ret"]:+.2f}%/월  {flag}')

    # ── 채택 종목 수익 시뮬레이션 ────────────────────────────────
    viable = [r for r in all_results if r['wr'] >= 45 and r['net_ev'] > 0]
    SEED   = {'KR': 1e7, 'US': 1e7, 'CRYPTO': 5e6}

    print()
    print('=' * 72)
    print('  채택 종목 수익 시뮬레이션')
    print('  시드: KR 1,000만 / US 1,000만 / CRYPTO 500만 = 총 2,500만원')
    print('=' * 72)

    total_won = 0.0
    for mkt in ['KR', 'US', 'CRYPTO']:
        grp = [r for r in viable if r['market'] == mkt]
        seed = SEED[mkt]
        if not grp:
            print(f'  [{mkt}] 채택 종목 없음')
            continue
        n_grp   = len(grp)
        alloc   = seed / n_grp
        mth_won = sum(r['mth_ret'] / 100 * alloc for r in grp)
        mth_pct = mth_won / seed * 100
        names   = ', '.join(r['name'] for r in grp)
        print(f'  [{mkt}] {n_grp}종목: {names}')
        print(f'    시드 {seed/1e4:,.0f}만 | 월수익 {mth_won/1e4:,.1f}만원 ({mth_pct:.2f}%/월)')
        total_won += mth_won

    total_seed = sum(SEED.values())
    total_pct  = total_won / total_seed * 100 if total_seed > 0 else 0

    print()
    print('=' * 72)
    print(f'  합계: 시드 {total_seed/1e4:,.0f}만원 | 월수익 {total_won/1e4:,.1f}만원 '
          f'({total_pct:.2f}%/월) | APY {total_pct*12:.1f}%')

    # 복리 12개월
    if total_pct > 0:
        print()
        print('  [복리 12개월 시뮬레이션]')
        capital = total_seed; cum = 0
        for m in range(1, 13):
            mo = capital * total_pct / 100
            capital += mo; cum += mo
            if m <= 3 or m == 6 or m == 12:
                print(f'    {m:2d}월  {capital/1e4:,.0f}만원  월+{mo/1e4:,.0f}만  누적+{cum/1e4:,.0f}만원')
    print('=' * 72)


if __name__ == '__main__':
    main()
