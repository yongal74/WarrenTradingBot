# -*- coding: utf-8 -*-
"""
CRYPTO 4H 백테스트 V2 — 즉시 재진입 로직 적용
================================================
핵심 수정:
  - 기존: 거래 후 MAX_HOLD(90봉=15일) 무조건 스킵 → 과소평가
  - 수정: 실제 보유 기간(j봉)만큼만 스킵 → 즉시 재진입
  - 원본 fvg_ob_tester.py 동일 FVG/OB 감지 (threshold 0.05%)
  - HTF 주봉 필터 ON/OFF 비교
  - 대상: BTC/ETH/SOL/XRP/BNB/DOGE 6종목
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, urllib.request

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SL_FLOOR    = 0.005
SL_CAP      = 0.030
RR          = 3.0
FEE         = 0.001
ZONE_EXPIRE = 20
MAX_HOLD    = 90   # 최대 보유 봉수 (상한선, 실제는 더 일찍 청산)

TICKERS = {
    'BTC-USD':  '비트코인',
    'ETH-USD':  '이더리움',
    'SOL-USD':  '솔라나',
    'XRP-USD':  '리플',
    'BNB-USD':  'BNB',
    'DOGE-USD': '도지코인',
}


def fetch(ticker):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval=1h&range=2y')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        r    = data.get('chart', {}).get('result', [])
        if not r: return None
        ts   = r[0]['timestamp']
        q    = r[0]['indicators']['quote'][0]
        df   = pd.DataFrame({
            'Open': q['open'], 'High': q['high'],
            'Low':  q['low'],  'Close': q.get('close', []),
            'Volume': q.get('volume', [None]*len(ts)),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except:
        return None


def resample_4h(df):
    return df.resample('4h').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    ).dropna()


def resample_weekly(df):
    return df.resample('W').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last'}
    ).dropna()


# ── 원본 fvg_ob_tester.py 동일 감지 로직 ──
def detect_zones(df):
    zones = []
    # FVG (threshold 0.05% = 원본과 동일)
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG','fi':i,'zh':lo0,'zl':hi2,'exp':i+ZONE_EXPIRE})
    # OB (하락봉 + 다음 2봉 임펄스 > 0.3%)
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB','fi':i,'zh':float(b['High']),'zl':float(b['Low']),'exp':i+ZONE_EXPIRE})
    return zones


def htf_ok(dfw, idx):
    """주봉 EMA20 위 여부"""
    if dfw is None or len(dfw) < 22: return True
    ema20 = float(dfw['Close'].ewm(span=20, adjust=False).mean().iloc[min(idx, len(dfw)-1)])
    last  = float(dfw['Close'].iloc[min(idx, len(dfw)-1)])
    return last > ema20


def backtest(ticker, name, df4h, dfw, use_htf=False):
    zones_all = detect_zones(df4h)
    trades = []
    i = 50  # 충분한 워밍업

    while i < len(df4h) - 1:
        row = df4h.iloc[i]
        cl  = float(row['Close'])
        lo  = float(row['Low'])
        op  = float(row['Open'])

        # 활성 존 찾기
        active = [z for z in zones_all if z['fi'] < i < z['exp']]
        hit = None
        for z in reversed(active):
            if lo <= z['zh'] and cl >= z['zl']:
                hit = z; break
        if not hit: i += 1; continue

        # Vol_Spike 필터
        vol   = df4h['Volume'].iloc[max(0, i-20):i]
        avg_v = float(vol.mean()) if len(vol) > 0 else 0
        cur_v = float(df4h['Volume'].iloc[i]) if df4h['Volume'].iloc[i] else 0
        if not (avg_v > 0 and cur_v > avg_v * 1.5): i += 1; continue

        # Body_In_Zone 필터
        body_low = min(cl, op)
        if not (body_low >= hit['zl'] * 0.998 and cl >= hit['zl']): i += 1; continue

        # Zone 중간 이상 마감
        zone_mid = hit['zl'] + (hit['zh'] - hit['zl']) * 0.5
        if cl < zone_mid: i += 1; continue

        # HTF 주봉 필터
        if use_htf:
            # 현재 시점에 해당하는 주봉 인덱스 추정
            w_idx = min(i // 42, len(dfw)-1)  # 4H봉 42개 ≈ 1주
            if not htf_ok(dfw, w_idx): i += 1; continue

        # SL/TP
        entry  = cl
        sl_pct = max(min((entry - hit['zl']) / entry, SL_CAP), SL_FLOOR)
        sl     = entry * (1 - sl_pct)
        tp     = entry * (1 + sl_pct * RR)

        # 결과 탐색 — 실제 보유 봉수(j)로 skip
        result = 'HOLD'; exit_p = None; hold_bars = MAX_HOLD
        for j in range(1, MAX_HOLD + 1):
            if i + j >= len(df4h): break
            fut = df4h.iloc[i + j]
            if float(fut['Low']) <= sl:
                result = 'LOSS'; exit_p = sl; hold_bars = j; break
            if float(fut['High']) >= tp:
                result = 'WIN';  exit_p = tp; hold_bars = j; break
        if result == 'HOLD':
            exit_p    = float(df4h.iloc[min(i+MAX_HOLD, len(df4h)-1)]['Close'])
            result    = 'WIN' if exit_p >= entry else 'LOSS'
            hold_bars = MAX_HOLD

        pnl = (exit_p - entry) / entry - FEE
        trades.append({'result': result, 'pnl': pnl * 100, 'hold': hold_bars})

        # ★ 핵심: 실제 보유 기간만큼만 skip (즉시 재진입 가능)
        i += hold_bars + 1

    if not trades: return None
    n    = len(trades)
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    wr   = wins / n * 100
    ev   = np.mean([t['pnl'] for t in trades])
    pnl_total = sum(t['pnl'] for t in trades)
    avg_hold  = np.mean([t['hold'] for t in trades])
    return {
        'ticker': ticker, 'name': name,
        'n': n, 'wr': wr, 'ev': ev, 'pnl': pnl_total,
        'mth_n': n / 24, 'mth_r': (n / 24) * ev,
        'avg_hold': avg_hold,
    }


def main():
    print('=' * 70)
    print('  CRYPTO 4H 백테스트 V2 — 즉시 재진입 로직 (실제 hold만큼 skip)')
    print('  원본 FVG/OB 0.05% | Vol_Spike+Body_In_Zone | R:R 1:3 | 수수료 0.10%')
    print('=' * 70)

    base_res = {}; htf_res = {}

    for ticker, name in TICKERS.items():
        print(f'  {name}({ticker})...', end='', flush=True)
        df1h = fetch(ticker)
        if df1h is None or len(df1h) < 500:
            print(' 데이터부족'); continue
        df4h = resample_4h(df1h)
        dfw  = resample_weekly(df1h)
        print(f' 4H={len(df4h)}봉', end='', flush=True)

        rb = backtest(ticker, name, df4h.copy(), dfw, use_htf=False)
        rh = backtest(ticker, name, df4h.copy(), dfw, use_htf=True)

        if rb:
            flag = '★' if rb['wr'] >= 55 and rb['ev'] > 0 else ' '
            print(f'\n    기본: {flag}{rb["n"]:3d}건 WR={rb["wr"]:5.1f}% EV={rb["ev"]:+.3f}% '
                  f'PnL={rb["pnl"]:+6.1f}% 평균보유={rb["avg_hold"]:.0f}봉')
            base_res[ticker] = rb
        if rh:
            flag = '★' if rh['wr'] >= 55 and rh['ev'] > 0 else ' '
            print(f'    HTF:  {flag}{rh["n"]:3d}건 WR={rh["wr"]:5.1f}% EV={rh["ev"]:+.3f}% '
                  f'PnL={rh["pnl"]:+6.1f}% 평균보유={rh["avg_hold"]:.0f}봉')
            htf_res[ticker] = rh
        if not rb: print(' 신호없음')
        print()

    # ── 요약 비교 ──
    print('=' * 70)
    print('  기본 vs HTF 비교 요약')
    print('=' * 70)
    print(f'  {"종목":<10} {"기본건/월":<9} {"기본WR":<8} {"기본EV":<10} '
          f'{"HTF건/월":<9} {"HTF WR":<8} {"HTF EV":<10} HTF효과')
    print(f'  {"-"*70}')

    total_base_mth = 0; total_htf_mth = 0
    valid_base = []; valid_htf = []

    for ticker, name in TICKERS.items():
        b = base_res.get(ticker)
        h = htf_res.get(ticker)
        if not b: continue
        dwr = (h['wr'] - b['wr']) if h else 0
        arr = '↑' if dwr > 0 else '↓'
        print(f'  {name:<10} {b["mth_n"]:5.1f}건    {b["wr"]:5.1f}%  {b["ev"]:+.3f}%     '
              f'{h["mth_n"] if h else 0:5.1f}건    '
              f'{h["wr"] if h else 0:5.1f}%  {h["ev"] if h else 0:+.3f}%     '
              f'{arr}{abs(dwr):.1f}%p')
        valid_base.append(b)
        if h: valid_htf.append(h)

    # ── 포트폴리오 수익 계산 ──
    print()
    print('=' * 70)
    print('  포트폴리오 월수익 시뮬레이션 (2.5억 균등배분)')
    print('=' * 70)

    seed = 2.5e8
    for label, results in [('기본(즉시재진입)', valid_base), ('HTF 필터+즉시재진입', valid_htf)]:
        if not results: continue
        n_coins = len(results)
        alloc   = seed / n_coins
        monthly_won = sum(r['mth_r'] / 100 * alloc for r in results)
        avg_wr  = np.mean([r['wr'] for r in results])
        mth_pct = monthly_won / seed * 100
        print(f'\n  [{label}] {n_coins}종목 균등배분')
        print(f'  평균 WR={avg_wr:.1f}%  월수익={monthly_won/1e4:,.0f}만원 ({mth_pct:.2f}%)')
        print()

        capital = seed; cum = 0
        for m in range(1, 13):
            mo = capital * mth_pct / 100
            capital += mo; cum += mo
            note = ' ★월1500만' if mo >= 1.5e7 else (' ★월1000만' if mo >= 1.0e7 else '')
            if m <= 4 or mo >= 8e6:
                print(f'    {m}월  {capital/1e8:.3f}억  월{mo/1e4:,.0f}만  누적+{cum/1e4:,.0f}만{note}')
        print(f'    12개월 후 시드: {capital/1e8:.2f}억 / 누적수익: {cum/1e4:,.0f}만원')


if __name__ == '__main__':
    main()
