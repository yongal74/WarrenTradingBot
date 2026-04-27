# -*- coding: utf-8 -*-
"""
Intraday Confluence Backtest — 5분봉 기준
- SL: 진입 캔들 저점 (구조적 손절, ~-0.3%)
- TP: 구조적 저항까지 거리의 25% 지점
- EOD: 장 마감 30분 전 강제 청산
- 진입 조건: 합류점 스코어 >= MIN_SCORE
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings; warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
from datetime import datetime

from config.assets import ALL_ASSETS
from core.confluence_engine import compute_score_series, MIN_SCORE, CONFLUENCE_IDS
from data.data_loader import load_intraday, load

# ── 백테스트 파라미터 ────────────────────────────────────────
MAX_SL_PCT    = -0.008   # SL 최대 -0.8% (구조적 SL이 너무 크면 캡)
MIN_SL_PCT    = -0.001   # SL 최소 -0.1% (너무 타이트 방지)
TP_RATIO      = 0.25     # 구조적 TP 거리의 25%
LOOKBACK_HIGH = 20       # 구조적 저항: 20봉 최고가
MAX_HOLD_BARS = 48       # 최대 보유: 48봉 = 4시간 (5분봉 기준)
EOD_CUTOFF_H  = 15       # EOD 진입 차단 시각 (시)
EOD_CUTOFF_M  = 30       # EOD 진입 차단 시각 (분) → 15:30 이후 진입 없음
FORCE_CLOSE_H = 15       # 강제 청산 시각 (시)
FORCE_CLOSE_M = 55       # 강제 청산 시각 (분) → 15:55 청산

RESULTS_DIR = Path(__file__).parent.parent / 'backtest_results'
RESULTS_DIR.mkdir(exist_ok=True)


def _is_eod_cutoff(ts: pd.Timestamp) -> bool:
    """신규 진입 불가 시간대 (15:30 이후)"""
    return (ts.hour > EOD_CUTOFF_H or
            (ts.hour == EOD_CUTOFF_H and ts.minute >= EOD_CUTOFF_M))


def _is_force_close(ts: pd.Timestamp) -> bool:
    """강제 청산 시각 (15:55 이후)"""
    return (ts.hour > FORCE_CLOSE_H or
            (ts.hour == FORCE_CLOSE_H and ts.minute >= FORCE_CLOSE_M))


def _structural_tp(df: pd.DataFrame, i: int) -> float:
    """
    진입 시점 i 기준, 과거 LOOKBACK_HIGH 봉의 최고가를 구조적 저항으로 사용
    """
    start = max(0, i - LOOKBACK_HIGH)
    return float(df['High'].iloc[start:i].max())


def backtest_single(ticker: str, market: str, conf_id: str) -> dict:
    """
    단일 종목 × 단일 합류점 전략 백테스트
    Returns: 통계 딕셔너리
    """
    # 5분봉 로드 (US), KR은 일봉 fallback
    if market == 'US':
        df = load_intraday(ticker, interval='5m')
    else:
        df = load(ticker, market)  # KR: 일봉 fallback

    if df is None or len(df) < 200:
        return _empty_stats(ticker, conf_id, reason='데이터부족')

    # DatetimeIndex 보장
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[df.index.notna()].copy()

    # 합류점 스코어 계산 (전체 시리즈)
    try:
        score_dict = compute_score_series(df)
    except Exception as e:
        return _empty_stats(ticker, conf_id, reason=f'스코어계산실패:{e}')

    scores = score_dict.get(conf_id, pd.Series(0, index=df.index))
    min_sc = MIN_SCORE[conf_id]

    trades = []
    in_position = False
    entry_price = 0.0
    entry_sl = 0.0
    entry_tp = 0.0
    entry_bar = 0
    entry_ts  = None

    for i in range(LOOKBACK_HIGH + 1, len(df) - 1):
        ts  = df.index[i]
        bar = df.iloc[i]

        # ── 포지션 보유 중 ───────────────────────────────────
        if in_position:
            hi = float(bar['High'])
            lo = float(bar['Low'])
            op = float(bar['Open'])

            # 갭다운 손절 (시가가 이미 SL 아래)
            if op <= entry_sl:
                exit_price = op
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                trades.append(_make_trade(ticker, conf_id, entry_ts, ts,
                                          entry_price, exit_price, pnl_pct, 'SL_GAP'))
                in_position = False
                continue

            # TP 도달
            if hi >= entry_tp:
                pnl_pct = (entry_tp - entry_price) / entry_price * 100
                trades.append(_make_trade(ticker, conf_id, entry_ts, ts,
                                          entry_price, entry_tp, pnl_pct, 'TP'))
                in_position = False
                continue

            # SL 도달
            if lo <= entry_sl:
                pnl_pct = (entry_sl - entry_price) / entry_price * 100
                trades.append(_make_trade(ticker, conf_id, entry_ts, ts,
                                          entry_price, entry_sl, pnl_pct, 'SL'))
                in_position = False
                continue

            # EOD 강제 청산
            if _is_force_close(ts):
                exit_price = float(bar['Close'])
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                trades.append(_make_trade(ticker, conf_id, entry_ts, ts,
                                          entry_price, exit_price, pnl_pct, 'EOD'))
                in_position = False
                continue

            # 최대 보유 기간 초과
            if i - entry_bar >= MAX_HOLD_BARS:
                exit_price = float(bar['Close'])
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                trades.append(_make_trade(ticker, conf_id, entry_ts, ts,
                                          entry_price, exit_price, pnl_pct, 'MAX_HOLD'))
                in_position = False
                continue

        # ── 진입 조건 체크 ───────────────────────────────────
        if not in_position:
            # EOD 차단
            if _is_force_close(ts) or _is_eod_cutoff(ts):
                continue

            score = int(scores.iloc[i]) if not pd.isna(scores.iloc[i]) else 0
            if score < min_sc:
                continue

            # 다음 봉 시가 진입
            next_bar = df.iloc[i + 1]
            entry_price = float(next_bar['Open'])
            if entry_price <= 0:
                continue

            # 구조적 SL: 진입 신호 캔들의 저점
            raw_sl = float(bar['Low'])
            sl_pct = (raw_sl - entry_price) / entry_price
            # SL 범위 캡 적용
            if sl_pct > MIN_SL_PCT:      # 너무 타이트 (저점이 시가와 거의 같음)
                sl_pct = MIN_SL_PCT
            if sl_pct < MAX_SL_PCT:      # 너무 넓음 → 캡
                sl_pct = MAX_SL_PCT
            entry_sl = entry_price * (1 + sl_pct)

            # 구조적 TP: 과거 LOOKBACK_HIGH 봉의 최고가까지 거리 × 25%
            resist = _structural_tp(df, i)
            if resist <= entry_price:
                # 저항이 없으면 (이미 최고가) ATR로 대체
                atr_arr = df['High'].rolling(14).max() - df['Low'].rolling(14).min()
                atr_val = float(atr_arr.iloc[i])
                resist  = entry_price + atr_val

            tp_dist   = resist - entry_price
            entry_tp  = entry_price + tp_dist * TP_RATIO

            # TP가 충분히 크지 않으면 스킵 (SL보다 TP가 작은 경우)
            if entry_tp <= entry_price + abs(entry_price - entry_sl) * 0.5:
                continue

            in_position = True
            entry_bar = i + 1
            entry_ts  = df.index[i + 1]

    # 미청산 포지션 강제 종료 (마지막 종가)
    if in_position:
        exit_price = float(df['Close'].iloc[-1])
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        trades.append(_make_trade(ticker, conf_id, entry_ts, df.index[-1],
                                  entry_price, exit_price, pnl_pct, 'END'))

    return _calc_stats(ticker, conf_id, trades)


def _make_trade(ticker, conf_id, entry_ts, exit_ts, entry, exit_, pnl_pct, reason):
    return {
        'ticker':   ticker,
        'conf':     conf_id,
        'entry_ts': entry_ts,
        'exit_ts':  exit_ts,
        'entry':    round(entry, 4),
        'exit':     round(exit_, 4),
        'pnl_pct':  round(pnl_pct, 4),
        'reason':   reason,
    }


def _calc_stats(ticker: str, conf_id: str, trades: list) -> dict:
    if not trades:
        return _empty_stats(ticker, conf_id, reason='거래없음')

    df_t = pd.DataFrame(trades)
    wins  = df_t[df_t['pnl_pct'] > 0]
    loses = df_t[df_t['pnl_pct'] <= 0]

    total    = len(df_t)
    win_cnt  = len(wins)
    wr       = win_cnt / total * 100
    avg_win  = float(wins['pnl_pct'].mean()) if len(wins) > 0 else 0.0
    avg_los  = float(loses['pnl_pct'].mean()) if len(loses) > 0 else 0.0
    total_pnl= float(df_t['pnl_pct'].sum())
    exp_val  = (wr/100 * avg_win) + ((1 - wr/100) * avg_los)

    gross_p  = wins['pnl_pct'].sum() if len(wins) > 0 else 0.0
    gross_l  = abs(loses['pnl_pct'].sum()) if len(loses) > 0 else 1e-9
    pf       = round(gross_p / gross_l, 3) if gross_l > 0 else 999.0

    # 이유별 카운트
    reason_cnt = df_t['reason'].value_counts().to_dict()

    return {
        'ticker':    ticker,
        'conf':      conf_id,
        'trades':    total,
        'win_rate':  round(wr, 1),
        'avg_win':   round(avg_win, 3),
        'avg_loss':  round(avg_los, 3),
        'exp_val':   round(exp_val, 4),
        'profit_factor': pf,
        'total_pnl': round(total_pnl, 3),
        'tp_cnt':    reason_cnt.get('TP', 0),
        'sl_cnt':    reason_cnt.get('SL', 0) + reason_cnt.get('SL_GAP', 0),
        'eod_cnt':   reason_cnt.get('EOD', 0),
        'max_hold_cnt': reason_cnt.get('MAX_HOLD', 0),
        'reason':    'OK',
    }


def _empty_stats(ticker, conf_id, reason=''):
    return {
        'ticker': ticker, 'conf': conf_id, 'trades': 0,
        'win_rate': 0, 'avg_win': 0, 'avg_loss': 0,
        'exp_val': 0, 'profit_factor': 0, 'total_pnl': 0,
        'tp_cnt': 0, 'sl_cnt': 0, 'eod_cnt': 0, 'max_hold_cnt': 0,
        'reason': reason,
    }


def run_all() -> pd.DataFrame:
    """15개 종목 × 5개 합류점 전체 백테스트"""
    results = []
    total = len(ALL_ASSETS) * len(CONFLUENCE_IDS)
    done  = 0

    print(f"\n{'='*60}")
    print(f"  5min Intraday Confluence Backtest")
    print(f"  SL: entry candle low (max -0.8%)")
    print(f"  TP: structural resistance x 25%")
    print(f"  EOD: cutoff 15:30 / force-close 15:55")
    print(f"  total {total} combinations")
    print(f"{'='*60}\n")

    for ticker, asset in ALL_ASSETS.items():
        market = asset['market']
        print(f"  [{ticker}] {asset['name']} ({market})")

        for conf_id in CONFLUENCE_IDS:
            stats = backtest_single(ticker, market, conf_id)
            results.append(stats)
            done += 1

            wr   = stats['win_rate']
            tr   = stats['trades']
            pf   = stats['profit_factor']
            ev   = stats['exp_val']
            rsn  = stats['reason']
            mark = '[OK]' if (tr >= 5 and wr >= 55 and pf >= 1.2) else '    '
            print(f"    {mark} {conf_id:<25} | "
                  f"trades={tr:>3} | WR={wr:>5.1f}% | PF={pf:>6.2f} | EV={ev:>+6.3f}% | {rsn}")

        print()

    return pd.DataFrame(results)


def save_and_summarize(df: pd.DataFrame):
    ts = datetime.now().strftime('%Y%m%d_%H%M')

    # 전체 결과 저장
    out_path = RESULTS_DIR / f'intraday_confluence_{ts}.csv'
    df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"\n  결과 저장: {out_path}")

    # 유효 거래만 필터
    valid = df[(df['trades'] >= 5) & (df['reason'] == 'OK')].copy()

    if valid.empty:
        print("  유효 거래 없음 (거래 수 < 5)")
        return

    # 요약: 합류점별 평균
    summary = valid.groupby('conf').agg(
        종목수=('ticker', 'count'),
        평균거래수=('trades', 'mean'),
        평균승률=('win_rate', 'mean'),
        평균PF=('profit_factor', 'mean'),
        평균EV=('exp_val', 'mean'),
        평균총손익=('total_pnl', 'mean'),
    ).round(2)
    print(f"\n{'='*60}")
    print("  합류점별 평균 성과 (5분봉 intraday)")
    print(f"{'='*60}")
    print(summary.to_string())

    # 종목별 최우수 전략
    best = valid.loc[valid.groupby('ticker')['exp_val'].idxmax()]
    best = best.sort_values('exp_val', ascending=False)
    print(f"\n{'='*60}")
    print("  종목별 최우수 합류점 전략")
    print(f"{'='*60}")
    for _, row in best.iterrows():
        print(f"  {row['ticker']:<8} | {row['conf']:<25} | "
              f"WR={row['win_rate']:>5.1f}% | PF={row['profit_factor']:>5.2f} | "
              f"EV={row['exp_val']:>+6.3f}% | 거래={row['trades']}")

    # 기대값 양수인 조합만 추출
    positive = valid[valid['exp_val'] > 0].sort_values('exp_val', ascending=False)
    print(f"\n  기대값 양수 조합: {len(positive)}개 / {len(valid)}개")

    # 저장
    summary.to_csv(RESULTS_DIR / f'intraday_summary_{ts}.csv', encoding='utf-8-sig')
    best.to_csv(RESULTS_DIR / f'intraday_best_{ts}.csv', index=False, encoding='utf-8-sig')
    positive.to_csv(RESULTS_DIR / f'intraday_positive_ev_{ts}.csv', index=False, encoding='utf-8-sig')

    print(f"\n  요약 파일 저장 완료: backtest_results/")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    df_results = run_all()
    save_and_summarize(df_results)
