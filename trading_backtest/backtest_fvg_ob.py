# -*- coding: utf-8 -*-
"""
FVG + Order Block 백테스트 (15분봉)
v2.0 Warren Trading System 기준

FVG  : 3봉 갭 불균형 구간 → 가격 되돌림시 진입
OB   : 충격파 직전 마지막 하락봉 → 가격 되돌림시 진입
RR   : 1:2 고정 (SL 1R, TP 2R)
SL   : FVG/OB 하단 아래 (구조적 손절)
EOD  : 15:30 진입차단 / 15:55 강제청산

C1 필터 (선택): DBB Bull zone + FVG + MSB + VolBreak + Engulfing
  → C1 score >= 4 일때만 진입 허용
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings; warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
from datetime import datetime

from config.assets import ALL_ASSETS
from data.data_loader import load_intraday, load
from core.confluence_engine import compute_score_series, _dbb_zone

RESULTS_DIR = Path(__file__).parent.parent / 'backtest_results'
RESULTS_DIR.mkdir(exist_ok=True)

# ── 파라미터 ─────────────────────────────────────────────────
RR_RATIO       = 2.0    # TP = SL * 2
MAX_SL_PCT     = 0.015  # SL 최대 1.5% (너무 넓은 구간 제외)
MIN_SL_PCT     = 0.001  # SL 최소 0.1% (너무 타이트 제외)
ZONE_EXPIRE    = 20     # 미체결 FVG/OB는 20봉 후 만료
EOD_CUTOFF_H   = 15
EOD_CUTOFF_M   = 30
FORCE_CLOSE_H  = 15
FORCE_CLOSE_M  = 55
MAX_HOLD_BARS  = 32     # 최대 보유: 32봉 = 8시간 (15분봉)
C1_MIN_SCORE   = 4      # C1 필터: 5개 중 4개 이상
# DBB: 20MA + 1std 상단 돌파 = Bull zone (shift(1)로 미래참조 방지)


def _is_eod(ts: pd.Timestamp) -> bool:
    return (ts.hour > EOD_CUTOFF_H or
            (ts.hour == EOD_CUTOFF_H and ts.minute >= EOD_CUTOFF_M))

def _is_force_close(ts: pd.Timestamp) -> bool:
    return (ts.hour > FORCE_CLOSE_H or
            (ts.hour == FORCE_CLOSE_H and ts.minute >= FORCE_CLOSE_M))


# ── FVG 감지 ──────────────────────────────────────────────────
def detect_fvg(df: pd.DataFrame) -> list:
    """
    Bullish FVG: candle[i-2].High < candle[i].Low
    → 갭 구간: (candle[i-2].High, candle[i].Low)
    → 가격이 갭 구간으로 되돌아왔을 때 진입
    """
    zones = []
    for i in range(2, len(df)):
        hi_2 = df['High'].iloc[i - 2]
        lo_0 = df['Low'].iloc[i]
        # Bullish FVG 조건: 직전-2봉 고점 < 현재봉 저점
        if lo_0 > hi_2 and (lo_0 - hi_2) / hi_2 > 0.0005:  # 갭 최소 0.05%
            zones.append({
                'type':       'FVG',
                'formed_i':   i,
                'zone_high':  lo_0,       # FVG 상단
                'zone_low':   hi_2,       # FVG 하단 (SL 기준)
                'mid':        (lo_0 + hi_2) / 2,
                'expire_i':   i + ZONE_EXPIRE,
            })
    return zones


# ── Order Block 감지 ──────────────────────────────────────────
def detect_ob(df: pd.DataFrame) -> list:
    """
    Bullish OB: 하락봉(close < open) 직후 강한 상승 발생
    → OB 구간: (하락봉.High, 하락봉.Low)
    → 가격이 OB 구간으로 되돌아왔을 때 진입
    """
    zones = []
    for i in range(1, len(df) - 2):
        bar = df.iloc[i]
        is_bearish = bar['Close'] < bar['Open']
        if not is_bearish:
            continue
        # 이후 2봉이 상승 충격파인지 확인
        impulse_hi  = df['High'].iloc[i + 1:i + 3].max()
        impulse_ret = (impulse_hi - bar['High']) / bar['High'] if bar['High'] > 0 else 0
        if impulse_ret > 0.003:   # 충격파 최소 0.3% 상승
            zones.append({
                'type':      'OB',
                'formed_i':  i,
                'zone_high': bar['High'],   # OB 상단 (진입 기준)
                'zone_low':  bar['Low'],    # OB 하단 (SL 기준)
                'mid':       (bar['High'] + bar['Low']) / 2,
                'expire_i':  i + ZONE_EXPIRE,
            })
    return zones


# ── 단일 종목 백테스트 ─────────────────────────────────────────
def backtest_single(ticker: str, market: str, use_c1: bool = False, use_dbb: bool = False) -> dict:
    # 15분봉 로드
    if market == 'US':
        df = load_intraday(ticker, interval='15m')
    else:
        df = load(ticker, market)   # KR fallback: 일봉

    if df is None or len(df) < 100:
        return _empty(ticker, 'US' if market == 'US' else 'KR', '데이터부족')

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[df.index.notna()].copy()

    # DBB 구간 시리즈 (필터용): 1=Bull zone, 0=Neutral, -1=Bear zone
    dbb_series = None
    if use_dbb:
        try:
            dbb_series = _dbb_zone(df)   # shift(1) 이미 적용됨
        except Exception:
            dbb_series = pd.Series(0, index=df.index)

    # C1 스코어 시리즈 (필터용)
    c1_scores = None
    if use_c1:
        try:
            score_dict = compute_score_series(df)
            c1_scores  = score_dict.get('C1_DBB_SmartMoney', pd.Series(0, index=df.index))
        except Exception:
            c1_scores = pd.Series(0, index=df.index)

    # FVG + OB 감지
    fvg_zones = detect_fvg(df)
    ob_zones  = detect_ob(df)
    all_zones = sorted(fvg_zones + ob_zones, key=lambda z: z['formed_i'])

    trades = []
    active_zones = []

    in_pos    = False
    entry_p   = 0.0
    tp_p      = 0.0
    sl_p      = 0.0
    entry_i   = 0
    entry_ts  = None
    zone_type = ''

    for i in range(3, len(df)):
        ts  = df.index[i]
        bar = df.iloc[i]
        hi  = float(bar['High'])
        lo  = float(bar['Low'])
        op  = float(bar['Open'])
        cl  = float(bar['Close'])

        # 새 구간 추가
        for z in all_zones:
            if z['formed_i'] == i - 1:
                active_zones.append(z)

        # 만료 구간 제거
        active_zones = [z for z in active_zones if z['expire_i'] > i]

        # ── 포지션 보유 중 ─────────────────────────────────────
        if in_pos:
            # 갭다운 손절
            if op <= sl_p:
                pnl = (op - entry_p) / entry_p * 100
                trades.append(_trade(ticker, zone_type, entry_ts, ts, entry_p, op, pnl, 'SL_GAP'))
                in_pos = False
                continue
            # TP
            if hi >= tp_p:
                pnl = (tp_p - entry_p) / entry_p * 100
                trades.append(_trade(ticker, zone_type, entry_ts, ts, entry_p, tp_p, pnl, 'TP'))
                in_pos = False
                continue
            # SL
            if lo <= sl_p:
                pnl = (sl_p - entry_p) / entry_p * 100
                trades.append(_trade(ticker, zone_type, entry_ts, ts, entry_p, sl_p, pnl, 'SL'))
                in_pos = False
                continue
            # EOD 강제청산
            if _is_force_close(ts):
                pnl = (cl - entry_p) / entry_p * 100
                trades.append(_trade(ticker, zone_type, entry_ts, ts, entry_p, cl, pnl, 'EOD'))
                in_pos = False
                continue
            # 최대보유
            if i - entry_i >= MAX_HOLD_BARS:
                pnl = (cl - entry_p) / entry_p * 100
                trades.append(_trade(ticker, zone_type, entry_ts, ts, entry_p, cl, pnl, 'MAX_HOLD'))
                in_pos = False
                continue

        # ── 진입 체크 ──────────────────────────────────────────
        if not in_pos and not _is_eod(ts) and not _is_force_close(ts):
            # DBB 필터: Bull zone(1)일 때만 진입
            if use_dbb and dbb_series is not None:
                if int(dbb_series.iloc[i]) != 1:
                    continue

            # C1 필터: 현재 봉의 C1 스코어 확인
            if use_c1 and c1_scores is not None:
                c1_val = int(c1_scores.iloc[i]) if not pd.isna(c1_scores.iloc[i]) else 0
                if c1_val < C1_MIN_SCORE:
                    continue

            for z in active_zones[:]:
                zh = z['zone_high']
                zl = z['zone_low']

                # 가격이 구간 안으로 들어왔는지 (되돌림)
                if lo <= zh and cl >= zl:
                    # 진입가: 구간 상단 또는 시가
                    entry_p = min(op, zh) if op <= zh else zh

                    sl_dist = entry_p - zl
                    sl_pct  = sl_dist / entry_p

                    # SL 범위 체크
                    if sl_pct < MIN_SL_PCT or sl_pct > MAX_SL_PCT:
                        continue

                    sl_p = entry_p - sl_dist
                    tp_p = entry_p + sl_dist * RR_RATIO   # 1:2

                    in_pos    = True
                    entry_i   = i
                    entry_ts  = ts
                    zone_type = z['type']
                    active_zones.remove(z)
                    break

    # 미청산 강제 종료
    if in_pos:
        cl = float(df['Close'].iloc[-1])
        pnl = (cl - entry_p) / entry_p * 100
        trades.append(_trade(ticker, zone_type, entry_ts, df.index[-1], entry_p, cl, pnl, 'END'))

    return _stats(ticker, market, trades)


def _trade(ticker, ztype, ets, xts, ep, xp, pnl, reason):
    return {
        'ticker': ticker, 'type': ztype,
        'entry_ts': ets, 'exit_ts': xts,
        'entry': round(ep, 4), 'exit': round(xp, 4),
        'pnl_pct': round(pnl, 4), 'reason': reason,
    }


def _stats(ticker: str, market: str, trades: list) -> dict:
    if not trades:
        return _empty(ticker, market, '거래없음')

    df_t  = pd.DataFrame(trades)
    wins  = df_t[df_t['pnl_pct'] > 0]
    loses = df_t[df_t['pnl_pct'] <= 0]
    total = len(df_t)
    wr    = len(wins) / total * 100
    avg_w = float(wins['pnl_pct'].mean())  if len(wins)  > 0 else 0.0
    avg_l = float(loses['pnl_pct'].mean()) if len(loses) > 0 else 0.0
    ev    = (wr / 100 * avg_w) + ((1 - wr / 100) * avg_l)
    gp    = wins['pnl_pct'].sum()  if len(wins)  > 0 else 0.0
    gl    = abs(loses['pnl_pct'].sum()) if len(loses) > 0 else 1e-9
    pf    = round(gp / gl, 3) if gl > 0 else 999.0
    rc    = df_t['reason'].value_counts().to_dict()
    by_t  = df_t.groupby('type')['pnl_pct'].agg(['count', 'mean']).to_dict()

    # FVG vs OB 분류
    fvg_cnt = int(df_t[df_t['type'] == 'FVG']['type'].count())
    ob_cnt  = int(df_t[df_t['type'] == 'OB']['type'].count())
    fvg_wr  = round(float(df_t[df_t['type'] == 'FVG']['pnl_pct'].gt(0).mean() * 100), 1) if fvg_cnt > 0 else 0.0
    ob_wr   = round(float(df_t[df_t['type'] == 'OB']['pnl_pct'].gt(0).mean() * 100), 1)  if ob_cnt  > 0 else 0.0

    return {
        'ticker':    ticker,
        'market':    market,
        'trades':    total,
        'win_rate':  round(wr, 1),
        'avg_win':   round(avg_w, 3),
        'avg_loss':  round(avg_l, 3),
        'exp_val':   round(ev, 4),
        'profit_factor': pf,
        'total_pnl': round(df_t['pnl_pct'].sum(), 3),
        'fvg_trades': fvg_cnt, 'fvg_wr': fvg_wr,
        'ob_trades':  ob_cnt,  'ob_wr':  ob_wr,
        'tp_cnt':    rc.get('TP', 0),
        'sl_cnt':    rc.get('SL', 0) + rc.get('SL_GAP', 0),
        'eod_cnt':   rc.get('EOD', 0),
        'reason':    'OK',
    }


def _empty(ticker, market, reason):
    return {
        'ticker': ticker, 'market': market, 'trades': 0,
        'win_rate': 0, 'avg_win': 0, 'avg_loss': 0,
        'exp_val': 0, 'profit_factor': 0, 'total_pnl': 0,
        'fvg_trades': 0, 'fvg_wr': 0, 'ob_trades': 0, 'ob_wr': 0,
        'tp_cnt': 0, 'sl_cnt': 0, 'eod_cnt': 0,
        'reason': reason,
    }


def _print_results(results: list, label: str):
    df = pd.DataFrame(results)
    valid = df[(df['trades'] >= 5) & (df['reason'] == 'OK')]
    print(f"\n  --- {label} 요약 ---")
    if not valid.empty:
        print(f"  유효종목:    {len(valid)}개")
        print(f"  평균 승률:   {valid['win_rate'].mean():.1f}%")
        print(f"  평균 PF:     {valid['profit_factor'].mean():.2f}")
        print(f"  기대값:      {valid['exp_val'].mean():+.4f}%/trade")
        print(f"  총손익(평균): {valid['total_pnl'].mean():+.2f}%")
        print(f"  기대값양수:  {(valid['exp_val'] > 0).sum()}/{len(valid)}")
    else:
        print("  유효 거래 없음")
    return df


def _run_mode(label, use_c1, use_dbb):
    results = []
    print(f"\n[{label}]\n")
    for ticker, asset in ALL_ASSETS.items():
        s = backtest_single(ticker, asset['market'], use_c1=use_c1, use_dbb=use_dbb)
        results.append(s)
        mark = '[+]' if s['trades'] >= 5 and s['exp_val'] > 0 else '   '
        print(f"  {mark} {ticker:<8} | n={s['trades']:>3} | WR={s['win_rate']:>5.1f}% | "
              f"PF={s['profit_factor']:>5.2f} | EV={s['exp_val']:>+6.3f}% | "
              f"FVG={s['fvg_trades']}({s['fvg_wr']}%) OB={s['ob_trades']}({s['ob_wr']}%)")
    return results


def _print_results(results, label):
    df = pd.DataFrame(results)
    valid = df[(df['trades'] >= 5) & (df['reason'] == 'OK')]
    print(f"\n  [{label} 요약]")
    if not valid.empty:
        print(f"  유효종목:{len(valid)} | 평균WR:{valid['win_rate'].mean():.1f}% | "
              f"평균PF:{valid['profit_factor'].mean():.2f} | "
              f"기대값:{valid['exp_val'].mean():+.4f}%/trade | "
              f"총손익(평균):{valid['total_pnl'].mean():+.2f}% | "
              f"양수:{(valid['exp_val']>0).sum()}/{len(valid)}")
    else:
        print("  유효 거래 없음 (n<5)")
    return df


def run_all():
    stamp = datetime.now().strftime('%Y%m%d_%H%M')

    print(f"\n{'='*72}")
    print(f"  FVG+OB 3종 비교 백테스트 (15분봉, R:R=1:{RR_RATIO})")
    print(f"  A: FVG+OB 단독")
    print(f"  B: FVG+OB + DBB Bull zone 필터")
    print(f"  C: FVG+OB + DBB + C1 필터 (>=4/5)")
    print(f"{'='*72}")

    res_a = _run_mode("A: FVG+OB 단독",         use_c1=False, use_dbb=False)
    df_a  = _print_results(res_a, "A")

    res_b = _run_mode("B: FVG+OB + DBB",         use_c1=False, use_dbb=True)
    df_b  = _print_results(res_b, "B")

    res_c = _run_mode("C: FVG+OB + DBB + C1",    use_c1=True,  use_dbb=True)
    df_c  = _print_results(res_c, "C")

    # ── 3종 비교표 ────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  3종 전략 비교  (n=거래수 / WR=승률 / EV=기대값/trade)")
    print(f"  {'ticker':<8} | {'A: FVG+OB':<22} | {'B: +DBB':<22} | {'C: +DBB+C1':<22}")
    print(f"  {'-'*8}-+-{'-'*22}-+-{'-'*22}-+-{'-'*22}")
    for a, b, c in zip(res_a, res_b, res_c):
        fa = f"n={a['trades']} WR={a['win_rate']:.0f}% EV={a['exp_val']:+.3f}%"
        fb = f"n={b['trades']} WR={b['win_rate']:.0f}% EV={b['exp_val']:+.3f}%"
        fc = f"n={c['trades']} WR={c['win_rate']:.0f}% EV={c['exp_val']:+.3f}%"
        # 3개 중 EV 최고 표시
        evs = [(a['exp_val'], a['trades']), (b['exp_val'], b['trades']), (c['exp_val'], c['trades'])]
        best_i = max(range(3), key=lambda i: evs[i][0] if evs[i][1] >= 3 else -999)
        flags = ['   ', '   ', '   ']
        if evs[best_i][1] >= 3: flags[best_i] = '***'
        print(f"  {a['ticker']:<8} | {fa:<22} | {fb:<22} | {fc:<22} {flags[2] if best_i==2 else (flags[1] if best_i==1 else '')}")
    print(f"{'='*80}\n")

    # 저장
    df_a['mode'] = 'A_FVG+OB'
    df_b['mode'] = 'B_FVG+OB+DBB'
    df_c['mode'] = 'C_FVG+OB+DBB+C1'
    df_all = pd.concat([df_a, df_b, df_c], ignore_index=True)
    out = RESULTS_DIR / f'fvg_ob_3way_compare_{stamp}.csv'
    df_all.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"  결과 저장: {out}")

    return df_a, df_b, df_c


if __name__ == '__main__':
    run_all()
