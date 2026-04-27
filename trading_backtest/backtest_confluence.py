# -*- coding: utf-8 -*-
"""
Confluence Backtest Engine
15종목 × 5개 합류점 전략 백테스트

진입 규칙:
  - 전일 합류 점수 >= 최소 기준 → 당일 시가 진입

청산 규칙:
  - actual_tp (TP 25% 지점) 도달 시 익절
  - actual_sl (1x ATR 손절) 도달 시 손절
  - MAX_HOLD일 초과 시 종가 청산

실행: python trading_backtest/backtest_confluence.py
"""
import warnings; warnings.filterwarnings('ignore')
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.data_loader import load
from core.confluence_engine import (
    compute_score_series, compute_tp_sl,
    CONFLUENCE_IDS, MIN_SCORE
)
from core.strategy_factory import _atr
from config.assets import ALL_ASSETS

MAX_HOLD = 10   # 최대 보유 일수

# ── 단일 백테스트 ───────────────────────────────────────────────
def backtest_single(ticker: str, market: str, conf_id: str) -> dict | None:
    df = load(ticker, market)
    if df is None or len(df) < 100:
        return None

    # DatetimeIndex 보장
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    scores  = compute_score_series(df)
    if conf_id not in scores:
        return None

    score_s = scores[conf_id]
    atr_s   = _atr(df)
    min_sc  = MIN_SCORE[conf_id]

    trades = []
    in_pos = False
    entry_price = actual_tp = actual_sl = 0.0
    entry_i = 0

    for i in range(60, len(df) - 1):
        if not in_pos:
            # 전일 합류 점수 확인 → 당일 시가 진입
            if score_s.iloc[i - 1] >= min_sc:
                ep  = float(df['Open'].iloc[i])
                atr = float(atr_s.iloc[i - 1])
                if atr <= 0 or np.isnan(atr) or ep <= 0:
                    continue
                tpsl = compute_tp_sl(ep, atr)
                entry_price = ep
                actual_tp   = tpsl['actual_tp']
                actual_sl   = tpsl['actual_sl']
                entry_i     = i
                in_pos      = True
        else:
            hi    = float(df['High'].iloc[i])
            lo    = float(df['Low'].iloc[i])
            op    = float(df['Open'].iloc[i])
            cl    = float(df['Close'].iloc[i])
            hold  = i - entry_i

            # 갭 다운 → 시가 손절
            if op <= actual_sl:
                trades.append(_trade(ticker, conf_id, entry_price, op, 'SL_GAP'))
                in_pos = False
                continue

            # TP 도달 (익절)
            if hi >= actual_tp and lo > actual_sl:
                trades.append(_trade(ticker, conf_id, entry_price, actual_tp, 'TP'))
                in_pos = False
                continue

            # SL 도달 (손절)
            if lo <= actual_sl:
                trades.append(_trade(ticker, conf_id, entry_price, actual_sl, 'SL'))
                in_pos = False
                continue

            # 최대 보유일 초과 → 종가 청산
            if hold >= MAX_HOLD:
                trades.append(_trade(ticker, conf_id, entry_price, cl, 'TIMEOUT'))
                in_pos = False

    if not trades:
        return None
    return _stats(ticker, conf_id, trades)


def _trade(ticker, conf_id, entry, exit_p, reason):
    pnl = (exit_p - entry) / entry * 100
    return {'ticker': ticker, 'confluence': conf_id,
            'entry': entry, 'exit': exit_p,
            'pnl_pct': pnl, 'reason': reason, 'win': pnl > 0}


def _stats(ticker, conf_id, trades):
    df = pd.DataFrame(trades)
    n    = len(df)
    wins = int(df['win'].sum())
    wr   = wins / n * 100

    total_ret = df['pnl_pct'].sum()
    avg_ret   = df['pnl_pct'].mean()
    avg_win   = df[df['win']]['pnl_pct'].mean()   if wins > 0        else 0.0
    avg_loss  = df[~df['win']]['pnl_pct'].mean()  if (n - wins) > 0  else 0.0

    gross_p = df[df['win']]['pnl_pct'].sum()
    gross_l = abs(df[~df['win']]['pnl_pct'].sum())
    pf      = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0

    cumret  = (1 + df['pnl_pct'] / 100).cumprod()
    peak    = cumret.cummax()
    mdd     = ((cumret - peak) / peak * 100).min()
    sharpe  = df['pnl_pct'].mean() / (df['pnl_pct'].std() + 1e-9)

    tp_cnt = (df['reason'] == 'TP').sum()
    sl_cnt = (df['reason'].isin(['SL', 'SL_GAP'])).sum()

    return {
        'Ticker':       ticker,
        'Confluence':   conf_id,
        'Trades':       n,
        'WinRate%':     round(wr, 1),
        'TotalRet%':    round(total_ret, 2),
        'AvgRet%':      round(avg_ret, 3),
        'AvgWin%':      round(avg_win, 3),
        'AvgLoss%':     round(avg_loss, 3),
        'MDD%':         round(mdd, 2),
        'ProfitFactor': pf,
        'Sharpe':       round(sharpe, 3),
        'TP_count':     int(tp_cnt),
        'SL_count':     int(sl_cnt),
    }


# ── 전체 백테스트 실행 ─────────────────────────────────────────
def run_all() -> pd.DataFrame:
    results = []
    total = len(ALL_ASSETS) * len(CONFLUENCE_IDS)
    done  = 0

    for ticker, asset in ALL_ASSETS.items():
        market = asset['market']
        for conf_id in CONFLUENCE_IDS:
            done += 1
            print(f"  [{done:>2}/{total}] {ticker:<8} × {conf_id} ...", end=' ', flush=True)
            r = backtest_single(ticker, market, conf_id)
            if r:
                results.append(r)
                print(f"WR={r['WinRate%']:.0f}% | {r['Trades']}건 | PF={r['ProfitFactor']}")
            else:
                print("데이터 부족")

    return pd.DataFrame(results) if results else pd.DataFrame()


# ── 결과 저장 + 요약 출력 ──────────────────────────────────────
def save_and_summarize(df: pd.DataFrame):
    out = Path(__file__).parent.parent / 'backtest_results'
    out.mkdir(exist_ok=True)

    df.to_csv(out / 'confluence_results.csv', index=False, encoding='utf-8-sig')

    # 전략별 요약
    summary = df.groupby('Confluence').agg(
        Trades      =('Trades',       'sum'),
        WinRate     =('WinRate%',     'mean'),
        TotalRet    =('TotalRet%',    'mean'),
        MDD         =('MDD%',         'mean'),
        ProfitFactor=('ProfitFactor', 'mean'),
        Sharpe      =('Sharpe',       'mean'),
    ).round(2).sort_values('WinRate', ascending=False)
    summary.to_csv(out / 'confluence_summary.csv', encoding='utf-8-sig')

    # 종목별 베스트 전략
    if len(df) > 0:
        best = (df.sort_values('WinRate%', ascending=False)
                  .groupby('Ticker').first()
                  .reset_index()[['Ticker','Confluence','WinRate%','TotalRet%','ProfitFactor','Trades']])
        best.to_csv(out / 'best_confluence_per_asset.csv', index=False, encoding='utf-8-sig')

    print(f"\n{'='*55}")
    print("  전략별 평균 성과")
    print('='*55)
    print(summary.to_string())
    print(f"\n결과 저장 완료: {out}")
    return summary


# ── 메인 ──────────────────────────────────────────────────────
if __name__ == '__main__':
    print('='*55)
    print('  Confluence Backtest')
    print('  15종목 × 5전략 | TP=25% | SL=1xATR | MAX_HOLD=10일')
    print(f'  실행시각: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('='*55)

    df_results = run_all()

    if df_results.empty:
        print("\n결과 없음 — 데이터 확인 필요")
    else:
        save_and_summarize(df_results)
