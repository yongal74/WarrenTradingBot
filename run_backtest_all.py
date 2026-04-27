# -*- coding: utf-8 -*-
"""
Warren 종합 백테스트 — 14종목 × 25전략 × 4타임프레임
타임프레임: 1m(+4h필터) / 5m / 15m / 4h
출력: backtest_results/all_results.csv
      backtest_results/strategy_ranking.csv
      backtest_results/top3_per_asset.csv
"""
import warnings; warnings.filterwarnings('ignore')
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

from core.strategy_factory import _compute_all

RESULTS_DIR = Path(__file__).parent / 'backtest_results'
RESULTS_DIR.mkdir(exist_ok=True)

# ── 유니버스 ──────────────────────────────────────────────────────
TICKERS = {
    '005930': ('삼성전자',    '005930.KS', 'KR'),
    '000660': ('SK하이닉스', '000660.KS', 'KR'),
    '009150': ('삼성전기',   '009150.KS', 'KR'),
    '034020': ('두산에너빌', '034020.KS', 'KR'),
    '008060': ('대덕전자',   '008060.KS', 'KR'),
    'NVDA':   ('엔비디아',   'NVDA',      'US'),
    'PLTR':   ('팔란티어',   'PLTR',      'US'),
    'AMD':    ('AMD',         'AMD',       'US'),
    'TSLA':   ('테슬라',     'TSLA',      'US'),
    'SOXX':   ('반도체ETF',  'SOXX',      'US'),
    'BTC':    ('비트코인',   'BTC-USD',   'CRYPTO'),
    'ETH':    ('이더리움',   'ETH-USD',   'CRYPTO'),
    'SOL':    ('솔라나',     'SOL-USD',   'CRYPTO'),
    'XRP':    ('리플',       'XRP-USD',   'CRYPTO'),
}

# ── 타임프레임 설정 ───────────────────────────────────────────────
TF_CONFIG = {
    '15m': {'interval': '15m', 'period': '60d',  'max_hold': 8,  'htf': None},
    '5m':  {'interval': '5m',  'period': '60d',  'max_hold': 16, 'htf': None},
    '4h':  {'interval': '1h',  'period': '730d', 'max_hold': 10, 'htf': None, 'resample': '4h'},
    '1m+4h': {'interval': '1m', 'period': '7d',  'max_hold': 30, 'htf': '4h'},
}

# FVG+OB 파라미터
RR_RATIO    = 2.0
MAX_SL_PCT  = 0.015
MIN_SL_PCT  = 0.001
ZONE_EXPIRE = 20


# ── 데이터 로드 ───────────────────────────────────────────────────
def _load(yf_ticker: str, interval: str, period: str) -> pd.DataFrame | None:
    try:
        df = yf.download(yf_ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        df = df[['Open','High','Low','Close','Volume']].dropna()
        return df if len(df) >= 30 else None
    except Exception:
        return None


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample('4h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min',
        'Close': 'last', 'Volume': 'sum'
    }).dropna()


# ── FVG + OB 감지 ─────────────────────────────────────────────────
def _detect_fvg(df):
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG','formed_i':i,'zone_high':lo0,
                          'zone_low':hi2,'expire_i':i+ZONE_EXPIRE})
    return zones


def _detect_ob(df):
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB','formed_i':i,'zone_high':float(b['High']),
                          'zone_low':float(b['Low']),'expire_i':i+ZONE_EXPIRE})
    return zones


# ── FVG+OB 백테스트 ───────────────────────────────────────────────
def _backtest_fvg_ob(df: pd.DataFrame, htf_trend: pd.Series = None) -> dict:
    """FVG+OB 전략 시뮬레이션. htf_trend=1이면 HTF 정배열 필터 적용"""
    all_zones = sorted(_detect_fvg(df) + _detect_ob(df), key=lambda z: z['formed_i'])
    trades = []
    active = []
    in_pos = False
    entry_p = sl_p = tp_p = 0.0
    entry_i = 0
    zone_type = ''

    for i in range(3, len(df)):
        bar = df.iloc[i]
        hi, lo, op, cl = float(bar['High']), float(bar['Low']), float(bar['Open']), float(bar['Close'])

        # HTF 필터 (1m+4h 모드)
        if htf_trend is not None:
            ts = df.index[i]
            trend_val = _get_htf_val(htf_trend, ts)
            if trend_val != 1:
                if in_pos and lo <= sl_p:
                    pnl = (op - entry_p) / entry_p * 100
                    trades.append({'pnl': min(pnl, -0.001), 'win': False, 'type': zone_type})
                    in_pos = False
                continue

        for z in all_zones:
            if z['formed_i'] == i - 1:
                active.append(z)
        active = [z for z in active if z['expire_i'] > i]

        if in_pos:
            if op <= sl_p:
                pnl = (op - entry_p) / entry_p * 100
                trades.append({'pnl': pnl, 'win': False, 'type': zone_type})
                in_pos = False; continue
            if hi >= tp_p:
                pnl = (tp_p - entry_p) / entry_p * 100
                trades.append({'pnl': pnl, 'win': True, 'type': zone_type})
                in_pos = False; continue
            if lo <= sl_p:
                pnl = (sl_p - entry_p) / entry_p * 100
                trades.append({'pnl': pnl, 'win': False, 'type': zone_type})
                in_pos = False; continue
            if i - entry_i >= 32:
                pnl = (cl - entry_p) / entry_p * 100
                trades.append({'pnl': pnl, 'win': pnl > 0, 'type': zone_type})
                in_pos = False
            continue

        for z in reversed(active):
            zh, zl = z['zone_high'], z['zone_low']
            if lo <= zh and cl >= zl:
                entry = min(op, zh) if op <= zh else zh
                sl_pct = (entry - zl) / entry if entry > 0 else 0
                if not (MIN_SL_PCT <= sl_pct <= MAX_SL_PCT):
                    continue
                entry_p = entry
                sl_p = entry - entry * sl_pct
                tp_p = entry + entry * sl_pct * RR_RATIO
                entry_i = i
                in_pos = True
                zone_type = z['type']
                break

    return _calc_metrics(trades)


def _get_htf_val(htf_series: pd.Series, ts: pd.Timestamp) -> int:
    """HTF 시리즈에서 ts 이전 최근값 반환"""
    try:
        idx = htf_series.index[htf_series.index <= ts]
        return int(htf_series[idx[-1]]) if len(idx) > 0 else 0
    except Exception:
        return 0


# ── 25전략 백테스트 ───────────────────────────────────────────────
def _backtest_strategy(df: pd.DataFrame, sig: pd.Series, max_hold: int) -> dict:
    """신호 시리즈 기반 단순 P&L 시뮬"""
    trades = []
    in_pos = False
    entry_p = 0.0
    hold = 0

    for i in range(1, len(df)):
        prev = int(sig.iloc[i-1]) if not pd.isna(sig.iloc[i-1]) else 0
        cur  = int(sig.iloc[i])   if not pd.isna(sig.iloc[i])   else 0

        if not in_pos:
            if prev == 0 and cur == 1:
                entry_p = float(df['Open'].iloc[i])
                in_pos = True
                hold = 0
        else:
            hold += 1
            if cur == 0 or hold >= max_hold:
                exit_p = float(df['Open'].iloc[i])
                pnl = (exit_p - entry_p) / entry_p * 100 if entry_p > 0 else 0
                trades.append({'pnl': pnl, 'win': pnl > 0, 'type': 'SIG'})
                in_pos = False

    return _calc_metrics(trades)


def _calc_metrics(trades: list) -> dict:
    if not trades:
        return {'trades': 0, 'win_rate': 0, 'total_pnl': 0,
                'avg_ret': 0, 'profit_factor': 0, 'mdd': 0, 'sharpe': 0}

    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    loss = [p for p in pnls if p <= 0]
    n = len(pnls)
    win_rate   = len(wins) / n * 100 if n > 0 else 0
    total_pnl  = sum(pnls)
    avg_ret    = total_pnl / n if n > 0 else 0
    pf         = sum(wins) / abs(sum(loss)) if loss and sum(loss) != 0 else (99 if wins else 0)
    std        = float(np.std(pnls)) if n > 1 else 1
    sharpe     = avg_ret / std if std > 0 else 0

    # MDD
    equity = np.cumsum(pnls)
    peak   = np.maximum.accumulate(equity)
    dd     = equity - peak
    mdd    = float(dd.min()) if len(dd) > 0 else 0

    return {
        'trades':        n,
        'win_rate':      round(win_rate, 1),
        'total_pnl':     round(total_pnl, 3),
        'avg_ret':       round(avg_ret, 4),
        'profit_factor': round(min(pf, 999), 3),
        'mdd':           round(mdd, 3),
        'sharpe':        round(sharpe, 4),
    }


# ── 메인 백테스트 루프 ────────────────────────────────────────────
def run_all():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*70}")
    print(f"  Warren 종합 백테스트 [{now}]")
    print(f"  14종목 × 25전략 × 4타임프레임 (1m+4h / 5m / 15m / 4h)")
    print(f"{'='*70}\n")

    all_rows = []
    total = len(TICKERS) * len(TF_CONFIG)
    done  = 0

    for code, (name, yf_tk, market) in TICKERS.items():
        print(f"  [{market}] {name}({code})")

        for tf_name, cfg in TF_CONFIG.items():
            done += 1
            print(f"    {tf_name} ({done}/{total})...", end=' ', flush=True)

            # 데이터 로드
            df = _load(yf_tk, cfg['interval'], cfg['period'])
            if df is None or len(df) < 30:
                print("데이터 없음")
                continue

            # 4h 리샘플
            if cfg.get('resample'):
                df = _resample_4h(df)
                if len(df) < 30:
                    print("리샘플 후 데이터 부족")
                    continue

            # HTF 트렌드 (1m+4h 전용)
            htf_trend = None
            if cfg.get('htf') == '4h':
                df_htf = _load(yf_tk, '1h', '30d')
                if df_htf is not None:
                    df4h = _resample_4h(df_htf)
                    e9  = df4h['Close'].ewm(span=9, adjust=False).mean()
                    e21 = df4h['Close'].ewm(span=21, adjust=False).mean()
                    htf_trend = (e9 > e21).astype(int)

            # FVG+OB
            m = _backtest_fvg_ob(df, htf_trend)
            all_rows.append({
                'Ticker': code, 'Name': name, 'Market': market,
                'Timeframe': tf_name, 'Strategy': 'FVG+OB',
                'Trades': m['trades'], 'WinRate%': m['win_rate'],
                'TotalRet%': m['total_pnl'], 'AvgRet%': m['avg_ret'],
                'ProfitFactor': m['profit_factor'],
                'MDD%': m['mdd'], 'Sharpe': m['sharpe'],
                '_tr': m['total_pnl'],
            })

            # 25전략
            if len(df) >= 60:
                try:
                    all_sigs = _compute_all(df)
                    for strat, sig in all_sigs.items():
                        m2 = _backtest_strategy(df, sig, cfg['max_hold'])
                        if m2['trades'] >= 2:
                            all_rows.append({
                                'Ticker': code, 'Name': name, 'Market': market,
                                'Timeframe': tf_name, 'Strategy': strat,
                                'Trades': m2['trades'], 'WinRate%': m2['win_rate'],
                                'TotalRet%': m2['total_pnl'], 'AvgRet%': m2['avg_ret'],
                                'ProfitFactor': m2['profit_factor'],
                                'MDD%': m2['mdd'], 'Sharpe': m2['sharpe'],
                                '_tr': m2['total_pnl'],
                            })
                except Exception as e:
                    print(f"전략계산오류:{e}", end=' ')

            print(f"완료 (FVG+OB: {m['trades']}건 WR={m['win_rate']:.0f}% PnL={m['total_pnl']:+.1f}%)")

    if not all_rows:
        print("\n  결과 없음")
        return

    df_all = pd.DataFrame(all_rows)

    # ── all_results.csv ──────────────────────────────────────────
    out_all = RESULTS_DIR / 'all_results.csv'
    df_all.to_csv(out_all, index=False, encoding='utf-8-sig')
    print(f"\n  [저장] all_results.csv ({len(df_all)}행)")

    # ── strategy_ranking.csv ─────────────────────────────────────
    ranking = (
        df_all[df_all['Trades'] >= 3]
        .groupby(['Strategy', 'Timeframe'])
        .agg(
            avg_ret  = ('TotalRet%', 'mean'),
            avg_sh   = ('Sharpe',    'mean'),
            avg_mdd  = ('MDD%',      'mean'),
            avg_wr   = ('WinRate%',  'mean'),
            avg_pf   = ('ProfitFactor', 'mean'),
            tickers  = ('Ticker',    'count'),
        )
        .reset_index()
        .sort_values('avg_ret', ascending=False)
    )
    ranking.to_csv(RESULTS_DIR / 'strategy_ranking.csv', index=False, encoding='utf-8-sig')
    print(f"  [저장] strategy_ranking.csv ({len(ranking)}행)")

    # ── top3_per_asset.csv ───────────────────────────────────────
    top3_rows = []
    for code, grp in df_all[df_all['Trades'] >= 3].groupby('Ticker'):
        top3 = grp.sort_values('TotalRet%', ascending=False).head(3)
        for _, row in top3.iterrows():
            top3_rows.append({
                'Ticker':       row['Ticker'],
                'Name':         row['Name'],
                'Market':       row['Market'],
                'Strategy':     row['Strategy'],
                'Timeframe':    row['Timeframe'],
                'WinRate%':     row['WinRate%'],
                'TotalRet%':    row['TotalRet%'],
                'ProfitFactor': row['ProfitFactor'],
                'Sharpe':       row['Sharpe'],
                'Trades':       row['Trades'],
            })
    df_top3 = pd.DataFrame(top3_rows)
    df_top3.to_csv(RESULTS_DIR / 'top3_per_asset.csv', index=False, encoding='utf-8-sig')
    print(f"  [저장] top3_per_asset.csv ({len(df_top3)}행)")

    # ── 요약 출력 ────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  백테스트 완료: {len(df_all)}건 결과")
    print(f"\n  [전략 TOP10 - 15분봉 기준]")
    top10 = ranking[ranking['Timeframe'] == '15m'].head(10)
    for _, r in top10.iterrows():
        print(f"    {r['Strategy']:<22} 평균수익={r['avg_ret']:+.2f}%  "
              f"WR={r['avg_wr']:.0f}%  Sharpe={r['avg_sh']:.2f}  종목={r['tickers']:.0f}개")

    print(f"\n  [FVG+OB 타임프레임별 평균]")
    fvg_rank = ranking[ranking['Strategy'] == 'FVG+OB']
    for _, r in fvg_rank.iterrows():
        print(f"    {r['Timeframe']:<8} 평균수익={r['avg_ret']:+.2f}%  "
              f"WR={r['avg_wr']:.0f}%  Sharpe={r['avg_sh']:.2f}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    run_all()
