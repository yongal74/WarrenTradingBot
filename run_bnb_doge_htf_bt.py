# -*- coding: utf-8 -*-
"""
BNB/DOGE 4H 원본 검증 + HTF(주봉) 필터 백테스트
=================================================
- fvg_ob_tester.py 와 동일한 FVG/OB 감지 로직 사용
  FVG threshold: 0.05% (원본과 동일)
  OB: 하락봉 + 다음 2봉 임펄스 > 0.3%
  ZONE_EXPIRE: 20봉
- 품질 필터: Vol_Spike(1.5x) + Body_In_Zone
- R:R 1:3 / SL zone기반(0.5~3%) / 수수료 0.10%
- HTF 필터: 주봉 EMA20 위 (큰 그림 상승 추세)
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, urllib.request
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 원본과 동일한 파라미터 ──
SL_FLOOR    = 0.005   # 0.5%
SL_CAP      = 0.030   # 3.0%
RR          = 3.0
FEE         = 0.001   # 0.10% 왕복
ZONE_EXPIRE = 20      # 봉 기준 (원본과 동일)
MAX_HOLD    = 90      # 4H 봉 기준 15일

TICKERS = {
    'BTC-USD':  '비트코인',
    'ETH-USD':  '이더리움',
    'SOL-USD':  '솔라나',
    'XRP-USD':  '리플',
    'BNB-USD':  'BNB',
    'DOGE-USD': '도지코인',
    'LTC-USD':  '라이트코인',
    'ADA-USD':  '에이다',
}


def fetch_v8(ticker: str, interval: str, range_: str) -> pd.DataFrame | None:
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
            'Open':   q['open'],  'High': q['high'],
            'Low':    q['low'],   'Close': q.get('close', []),
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except:
        return None


def get_4h_and_weekly(ticker: str):
    """1H 데이터 → 4H 리샘플 + 주봉 리샘플"""
    df1h = fetch_v8(ticker, '1h', '2y')
    if df1h is None or len(df1h) < 500:
        return None, None
    df4h = df1h.resample('4h').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    ).dropna()
    dfw = df1h.resample('W').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    ).dropna()
    return df4h, dfw


# ── 원본 fvg_ob_tester.py와 동일한 감지 함수 ──

def detect_fvg(df: pd.DataFrame) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        # 원본: threshold 0.0005 (0.05%)
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({
                'type': 'FVG', 'formed_i': i,
                'zone_high': lo0, 'zone_low': hi2,
                'expire_i': i + ZONE_EXPIRE,
            })
    return zones


def detect_ob(df: pd.DataFrame) -> list:
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue  # 양봉 스킵
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({
                'type': 'OB', 'formed_i': i,
                'zone_high': float(b['High']),
                'zone_low':  float(b['Low']),
                'expire_i':  i + ZONE_EXPIRE,
            })
    return zones


def quality_filters(df: pd.DataFrame, i: int, entry: float, zone_low: float) -> dict:
    """Vol_Spike + Body_In_Zone (원본 핵심 필터)"""
    vol   = df['Volume'].iloc[max(0, i-20):i]
    avg_v = float(vol.mean()) if len(vol) > 0 else 0
    cur_v = float(df['Volume'].iloc[i]) if df['Volume'].iloc[i] else 0

    bar      = df.iloc[i]
    bar_cl   = float(bar['Close'])
    bar_op   = float(bar['Open'])
    body_low = min(bar_cl, bar_op)

    vol_spike    = (avg_v > 0 and cur_v > avg_v * 1.5)
    body_in_zone = (body_low >= zone_low * 0.998 and bar_cl >= zone_low)

    return {'vol_spike': vol_spike, 'body_in_zone': body_in_zone}


def weekly_htf_ok(dfw: pd.DataFrame, bar_time) -> bool:
    """주봉 HTF 필터: 해당 시점 주봉이 EMA20 위인지 확인"""
    if dfw is None or len(dfw) < 25:
        return True  # 데이터 없으면 통과
    # 해당 4H 봉 시점 이전의 주봉 찾기
    past_weeks = dfw[dfw.index <= bar_time]
    if len(past_weeks) < 21:
        return True
    ema20w = past_weeks['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    last_w_close = float(past_weeks['Close'].iloc[-1])
    return last_w_close > float(ema20w)


def backtest_ticker(ticker: str, name: str, df4h: pd.DataFrame,
                    dfw: pd.DataFrame, use_htf: bool = False) -> dict | None:
    all_zones = detect_fvg(df4h) + detect_ob(df4h)
    all_zones.sort(key=lambda z: z['formed_i'])

    trades = []; i = 200
    while i < len(df4h) - 1:
        row  = df4h.iloc[i]
        cl   = float(row['Close'])
        lo   = float(row['Low'])
        op   = float(row['Open'])
        time = df4h.index[i]

        active = [z for z in all_zones if z['formed_i'] < i < z['expire_i']]
        hit = None
        for z in reversed(active):
            if lo <= z['zone_high'] and cl >= z['zone_low']:
                hit = z; break
        if not hit: i += 1; continue

        # 품질 필터
        qf = quality_filters(df4h, i, cl, hit['zone_low'])
        if not (qf['vol_spike'] and qf['body_in_zone']): i += 1; continue

        # zone 중간 이상 마감 확인
        zone_mid = hit['zone_low'] + (hit['zone_high'] - hit['zone_low']) * 0.5
        if cl < zone_mid: i += 1; continue

        # HTF 필터
        if use_htf and not weekly_htf_ok(dfw, time): i += 1; continue

        # SL/TP 계산
        entry  = cl
        sl_pct = max(min((entry - hit['zone_low']) / entry, SL_CAP), SL_FLOOR)
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + sl_pct * RR)

        # 결과 탐색
        result = 'HOLD'; exit_p = None
        for j in range(1, MAX_HOLD + 1):
            if i + j >= len(df4h): break
            fut = df4h.iloc[i + j]
            if float(fut['Low']) <= sl:   result = 'LOSS'; exit_p = sl; break
            if float(fut['High']) >= tp:  result = 'WIN';  exit_p = tp; break
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
    return {
        'ticker': ticker, 'name': name,
        'n': n, 'wr': wr, 'ev': ev,
        'pnl': pnl_total,
        'mth_n': n / 24,
        'mth_r': (n / 24) * ev,
    }


def main():
    print('=' * 68)
    print('  BNB/DOGE 원본 검증 + HTF 주봉 필터 백테스트')
    print('  원본 fvg_ob_tester.py 동일 로직 | R:R 1:3 | 수수료 0.10%')
    print('=' * 68)

    base_results = {}
    htf_results  = {}

    for ticker, name in TICKERS.items():
        print(f'  {name}({ticker}) 데이터 수신...', end='', flush=True)
        df4h, dfw = get_4h_and_weekly(ticker)
        if df4h is None or len(df4h) < 250:
            print(' 데이터 부족'); continue
        print(f' 4H={len(df4h)}봉 주봉={len(dfw) if dfw is not None else 0}봉', end='', flush=True)

        r_base = backtest_ticker(ticker, name, df4h, dfw, use_htf=False)
        r_htf  = backtest_ticker(ticker, name, df4h, dfw, use_htf=True)

        if r_base:
            flag = '★' if r_base['wr'] >= 55 and r_base['ev'] > 0 else ' '
            print(f'\n    기본: {flag}{r_base["n"]}건 WR={r_base["wr"]:.1f}% '
                  f'EV={r_base["ev"]:+.3f}% PnL={r_base["pnl"]:+.1f}%', end='')
            base_results[ticker] = r_base
        if r_htf:
            flag2 = '★' if r_htf['wr'] >= 55 and r_htf['ev'] > 0 else ' '
            print(f'\n    HTF:  {flag2}{r_htf["n"]}건 WR={r_htf["wr"]:.1f}% '
                  f'EV={r_htf["ev"]:+.3f}% PnL={r_htf["pnl"]:+.1f}%', end='')
            htf_results[ticker] = r_htf
        print()

    # ── 결과 요약 ──
    print()
    print('=' * 68)
    print('  기본 vs HTF 필터 비교')
    print('=' * 68)
    print(f'  {"종목":<12} {"기본WR":<9} {"기본EV":<10} {"HTF WR":<9} {"HTF EV":<10} {"HTF효과"}')
    print(f'  {"-"*65}')

    ref_4h = {
        'BTC-USD': (58.0, 57.7, 158),
        'ETH-USD': (57.0, 51.1, 170),
        'SOL-USD': (65.0, 77.9, 136),
        'XRP-USD': (62.0, 80.4, 152),
    }

    all_base = []; all_htf = []
    for ticker in TICKERS:
        name = TICKERS[ticker]
        b = base_results.get(ticker)
        h = htf_results.get(ticker)
        if not b: continue

        # 원본 검증된 수치가 있으면 병기
        if ticker in ref_4h:
            ref_wr, ref_pnl, ref_n = ref_4h[ticker]
            ref_ev = ref_pnl / ref_n
            note = f' (원본검증:{ref_wr:.0f}%/{ref_ev:+.2f}%)'
        else:
            note = ' ★신규'

        htf_wr  = h['wr'] if h else 0
        htf_ev  = h['ev'] if h else 0
        dwr = htf_wr - b['wr'] if h else 0
        arr = '↑' if dwr > 0 else '↓'
        print(f'  {name:<12} {b["wr"]:5.1f}%   {b["ev"]:+.4f}%   '
              f'{htf_wr:5.1f}%   {htf_ev:+.4f}%   {arr}{abs(dwr):.1f}%p{note}')
        all_base.append(b)
        if h: all_htf.append(h)

    # ── 편입 판정 ──
    print()
    print('=' * 68)
    print('  편입 판정 (WR>=55%, EV>0 기준)')
    print('=' * 68)
    ok_tickers = []
    for ticker in TICKERS:
        name = TICKERS[ticker]
        b = base_results.get(ticker)
        if not b: continue
        ok = b['wr'] >= 55 and b['ev'] > 0
        flag = '★ 편입' if ok else '  제외'
        mth_won = b['mth_r'] / 100 * 2.5e8 / 6 / 1e4  # 6종목 균등배분 기준
        print(f'  {flag} {name:<10} WR={b["wr"]:.1f}% EV={b["ev"]:+.3f}% '
              f'월수익률={b["mth_r"]:+.3f}% '
              f'(2.5억/6종목 기준 월{mth_won:,.0f}만)')
        if ok:
            ok_tickers.append(b)

    # ── 최적 포트폴리오 월수익 ──
    if ok_tickers:
        print()
        print('=' * 68)
        print('  최적 포트폴리오 수익 시뮬레이션')
        print('=' * 68)
        n_ok = len(ok_tickers)
        seed = 2.5e8
        alloc = seed / n_ok
        total_monthly = sum(r['mth_r'] / 100 * alloc for r in ok_tickers)
        avg_wr = np.mean([r['wr'] for r in ok_tickers])
        print(f'  편입 종목: {n_ok}개 | 균등 배분 {alloc/1e4:,.0f}만씩')
        print(f'  평균 WR: {avg_wr:.1f}% | 월 합산 수익: {total_monthly/1e4:,.0f}만원')
        print()
        print(f'  {"월":<5} {"시드":<13} {"월수익":<12} {"누적"}')
        print(f'  {"-"*45}')
        capital = seed; cum = 0
        mth_pct = total_monthly / seed
        for m in range(1, 13):
            mo = capital * mth_pct
            capital += mo; cum += mo
            note = ' ★월1000만' if mo >= 1e7 else (' ←목표' if mo >= 1.5e7 else '')
            if m <= 6 or mo >= 8e6:
                print(f'  {m}월    {capital/1e8:.3f}억     {mo/1e4:>6,.0f}만원    +{cum/1e4:,.0f}만원{note}')
    else:
        print('\n  WR>=55% 편입 종목 없음. 조건 완화(WR>=50%) 시 재검토 필요.')

    # CSV 저장
    rows = []
    for ticker, b in base_results.items():
        h = htf_results.get(ticker, {})
        rows.append({
            'ticker': ticker, 'name': TICKERS[ticker],
            'base_n': b['n'], 'base_wr': round(b['wr'],1),
            'base_ev': round(b['ev'],4), 'base_pnl': round(b['pnl'],1),
            'htf_n':  h.get('n',0), 'htf_wr': round(h.get('wr',0),1),
            'htf_ev': round(h.get('ev',0),4),
        })
    out = Path('logs/bnb_doge_htf_bt.csv')
    pd.DataFrame(rows).to_csv(out, index=False, encoding='utf-8-sig')
    print(f'\n  결과 저장: {out}')


if __name__ == '__main__':
    main()
