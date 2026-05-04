# -*- coding: utf-8 -*-
"""
스윙 백테스트: FVG+OB vs FVG+OB+DBB 비교
- 일봉 기준, 보유 최대 15일
- 시장별 수수료 적용 (KR 0.23%, US 0.50%)
- 결과: 승률 / 수익 (수수료 전·후) / MDD / 평균 보유일
"""
import sys
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ── 파라미터 ──────────────────────────────────────────────────
PERIOD       = '1y'          # 1년 일봉
SL_PCT       = 0.03          # SL 3%
TP_PCT       = 0.06          # TP 6% (R:R 1:2)
MAX_HOLD     = 15            # 최대 보유일
ZONE_EXPIRE  = 30            # 존 유효 봉 수
FEE = {'KR': 0.0023, 'US': 0.0050}  # 왕복 수수료

# DBB 파라미터
BB_PERIOD = 20
BB1_STD   = 1.0   # 안쪽 밴드
BB2_STD   = 2.0   # 바깥쪽 밴드

# ── 유니버스 ──────────────────────────────────────────────────
UNIVERSE = {
    # KR
    '005930.KS': ('삼성전자',    'KR'),
    '000660.KS': ('SK하이닉스', 'KR'),
    '009150.KS': ('삼성전기',   'KR'),
    '034020.KS': ('두산에너빌', 'KR'),
    '008060.KS': ('대덕전자',   'KR'),
    # US
    'NVDA':  ('엔비디아',  'US'),
    'PLTR':  ('팔란티어', 'US'),
    'AMD':   ('AMD',      'US'),
    'TSLA':  ('테슬라',   'US'),
    'SOXX':  ('반도체ETF','US'),
}


# ── 지표 계산 ────────────────────────────────────────────────
def _add_dbb(df: pd.DataFrame) -> pd.DataFrame:
    """Double Bollinger Bands 추가"""
    ma = df['Close'].rolling(BB_PERIOD).mean()
    sd = df['Close'].rolling(BB_PERIOD).std()
    df = df.copy()
    df['bb1_upper'] = ma + BB1_STD * sd
    df['bb1_lower'] = ma - BB1_STD * sd
    df['bb2_upper'] = ma + BB2_STD * sd
    df['bb2_lower'] = ma - BB2_STD * sd
    df['bb_mid']    = ma
    return df


def _in_dbb_buy_zone(row) -> bool:
    """DBB 매수 구간: 종가가 BB1하단 이하 (과매도 영역)"""
    try:
        return float(row['Close']) <= float(row['bb1_lower'])
    except Exception:
        return False


# ── FVG 감지 (일봉) ──────────────────────────────────────────
def _detect_fvg_daily(df: pd.DataFrame) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.003:
            zones.append({
                'type': 'FVG', 'formed_i': i,
                'zone_high': lo0, 'zone_low': hi2,
                'expire_i': i + ZONE_EXPIRE,
            })
    return zones


# ── OB 감지 (일봉) ───────────────────────────────────────────
def _detect_ob_daily(df: pd.DataFrame) -> list:
    zones = []
    for i in range(1, len(df) - 2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']):
            continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.005:
            zones.append({
                'type': 'OB', 'formed_i': i,
                'zone_high': float(b['High']),
                'zone_low':  float(b['Low']),
                'expire_i':  i + ZONE_EXPIRE,
            })
    return zones


# ── 백테스트 엔진 ─────────────────────────────────────────────
def _run_bt(df: pd.DataFrame, market: str, use_dbb: bool) -> list:
    """
    단일 종목 백테스트
    Returns: list of trade dicts
    """
    if len(df) < BB_PERIOD + 10:
        return []

    df = _add_dbb(df)
    fvg_zones = _detect_fvg_daily(df)
    ob_zones  = _detect_ob_daily(df)
    all_zones = fvg_zones + ob_zones

    fee = FEE.get(market, 0.005)
    trades = []
    in_trade = False
    entry_i = -1

    for i in range(BB_PERIOD, len(df)):
        if in_trade:
            row  = df.iloc[i]
            hi   = float(row['High'])
            lo   = float(row['Low'])
            days = i - entry_i

            # TP/SL/최대보유 청산
            if hi >= tp_price:
                pnl_gross = TP_PCT
                pnl_net   = pnl_gross - fee
                trades.append({
                    'result': 'WIN', 'reason': 'TP',
                    'pnl_gross': pnl_gross, 'pnl_net': pnl_net,
                    'hold_days': days, 'market': market,
                    'zone_type': entry_zone_type,
                })
                in_trade = False
            elif lo <= sl_price:
                pnl_gross = -SL_PCT
                pnl_net   = pnl_gross - fee
                trades.append({
                    'result': 'LOSS', 'reason': 'SL',
                    'pnl_gross': pnl_gross, 'pnl_net': pnl_net,
                    'hold_days': days, 'market': market,
                    'zone_type': entry_zone_type,
                })
                in_trade = False
            elif days >= MAX_HOLD:
                cl = float(df['Close'].iloc[i])
                pnl_gross = (cl - entry_price) / entry_price
                pnl_net   = pnl_gross - fee
                trades.append({
                    'result': 'WIN' if pnl_gross > 0 else 'LOSS',
                    'reason': 'MAX_HOLD',
                    'pnl_gross': pnl_gross, 'pnl_net': pnl_net,
                    'hold_days': days, 'market': market,
                    'zone_type': entry_zone_type,
                })
                in_trade = False
            continue

        # 진입 조건 탐색
        row = df.iloc[i]
        op  = float(row['Open'])
        cl  = float(row['Close'])
        lo  = float(row['Low'])
        hi  = float(row['High'])

        for z in all_zones:
            if z['formed_i'] >= i or z['expire_i'] < i:
                continue
            zh = z['zone_high']
            zl = z['zone_low']
            # 존 터치: 저점이 존에 닿고 종가가 존 위로 마감
            if not (lo <= zh and cl >= zl):
                continue
            # DBB 필터
            if use_dbb and not _in_dbb_buy_zone(row):
                continue

            # 진입
            in_trade        = True
            entry_i         = i
            entry_price     = cl
            tp_price        = cl * (1 + TP_PCT)
            sl_price        = cl * (1 - SL_PCT)
            entry_zone_type = z['type']
            break

    return trades


# ── 성과 요약 ─────────────────────────────────────────────────
def _summary(trades: list, label: str) -> dict:
    if not trades:
        return {'label': label, 'count': 0}

    df = pd.DataFrame(trades)
    wins = df[df['result'] == 'WIN']
    wr   = len(wins) / len(df) * 100

    gross_total = df['pnl_gross'].sum() * 100
    net_total   = df['pnl_net'].sum() * 100

    # MDD 계산 (누적 수익 기준)
    cum = df['pnl_net'].cumsum()
    roll_max = cum.cummax()
    mdd = ((cum - roll_max) / (1 + roll_max)).min() * 100

    avg_hold = df['hold_days'].mean()

    # 존 타입별 승률
    for ztype in ('FVG', 'OB'):
        sub = df[df['zone_type'] == ztype]
        wr_z = len(sub[sub['result'] == 'WIN']) / len(sub) * 100 if len(sub) else 0

    return {
        'label':        label,
        'count':        len(df),
        'win_rate':     round(wr, 1),
        'gross_pnl':    round(gross_total, 2),
        'net_pnl':      round(net_total, 2),
        'mdd':          round(mdd, 2),
        'avg_hold_days':round(avg_hold, 1),
        'fvg_count':    len(df[df['zone_type'] == 'FVG']),
        'ob_count':     len(df[df['zone_type'] == 'OB']),
    }


# ── 메인 ─────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  스윙 백테스트: FVG+OB  vs  FVG+OB+DBB")
    print(f"  기간: {PERIOD} 일봉 | SL {SL_PCT*100:.0f}% / TP {TP_PCT*100:.0f}% | 최대{MAX_HOLD}일 보유")
    print("=" * 65)

    all_v1, all_v2 = [], []   # v1=FVG+OB, v2=FVG+OB+DBB
    rows = []

    for yf_tk, (name, market) in UNIVERSE.items():
        try:
            df = yf.download(yf_tk, period=PERIOD, interval='1d',
                             auto_adjust=True, progress=False)
            if df is None or df.empty or len(df) < 60:
                print(f"  [{market}] {name}: 데이터 부족")
                continue
            if hasattr(df.columns, 'levels'):
                df.columns = df.columns.droplevel(1)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df = df[['Open','High','Low','Close','Volume']].dropna()
        except Exception as e:
            print(f"  [{market}] {name}: 다운로드 실패 ({e})")
            continue

        t_v1 = _run_bt(df, market, use_dbb=False)
        t_v2 = _run_bt(df, market, use_dbb=True)
        all_v1.extend(t_v1)
        all_v2.extend(t_v2)

        s1 = _summary(t_v1, 'FVG+OB')
        s2 = _summary(t_v2, 'FVG+OB+DBB')

        fee = FEE.get(market, 0)
        print(f"\n  [{market}] {name} ({yf_tk})")
        print(f"    FVG+OB      : {s1['count']:3d}건 | WR {s1.get('win_rate',0):5.1f}% | "
              f"수수료전 {s1.get('gross_pnl',0):+7.2f}% | 수수료후 {s1.get('net_pnl',0):+7.2f}% | "
              f"MDD {s1.get('mdd',0):+6.2f}% | 평균{s1.get('avg_hold_days',0):.1f}일")
        print(f"    FVG+OB+DBB  : {s2['count']:3d}건 | WR {s2.get('win_rate',0):5.1f}% | "
              f"수수료전 {s2.get('gross_pnl',0):+7.2f}% | 수수료후 {s2.get('net_pnl',0):+7.2f}% | "
              f"MDD {s2.get('mdd',0):+6.2f}% | 평균{s2.get('avg_hold_days',0):.1f}일")

        rows.append({
            'market': market, 'name': name,
            'v1_cnt': s1.get('count',0), 'v1_wr': s1.get('win_rate',0),
            'v1_gross': s1.get('gross_pnl',0), 'v1_net': s1.get('net_pnl',0), 'v1_mdd': s1.get('mdd',0),
            'v2_cnt': s2.get('count',0), 'v2_wr': s2.get('win_rate',0),
            'v2_gross': s2.get('gross_pnl',0), 'v2_net': s2.get('net_pnl',0), 'v2_mdd': s2.get('mdd',0),
        })

    # ── 전체 합산 요약 ─────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  [전체 합산 결과]")
    print("=" * 65)

    for label, trades in [('FVG+OB     ', all_v1), ('FVG+OB+DBB ', all_v2)]:
        if not trades:
            print(f"  {label}: 데이터 없음")
            continue
        s = _summary(trades, label)
        ev = s['net_pnl'] / s['count'] if s['count'] else 0
        print(f"  {label}: {s['count']:3d}건 | WR {s['win_rate']:5.1f}% | "
              f"수수료전 {s['gross_pnl']:+7.2f}% | 수수료후 {s['net_pnl']:+7.2f}% | "
              f"MDD {s['mdd']:+6.2f}% | EV/트레이드 {ev:+.3f}%")

    # ── 시장별 합산 ────────────────────────────────────────────
    for mkt in ('KR', 'US'):
        t1 = [t for t in all_v1 if t['market'] == mkt]
        t2 = [t for t in all_v2 if t['market'] == mkt]
        s1 = _summary(t1, f'{mkt} FVG+OB')
        s2 = _summary(t2, f'{mkt} FVG+OB+DBB')
        print(f"\n  [{mkt}] FVG+OB      : {s1.get('count',0):3d}건 | WR {s1.get('win_rate',0):5.1f}% | 수수료후 {s1.get('net_pnl',0):+7.2f}%")
        print(f"  [{mkt}] FVG+OB+DBB  : {s2.get('count',0):3d}건 | WR {s2.get('win_rate',0):5.1f}% | 수수료후 {s2.get('net_pnl',0):+7.2f}%")

    # ── 결론 ────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  [수수료 분석]")
    print(f"  KR 스윙 수수료: {FEE['KR']*100:.2f}% (왕복) → TP 6%면 순수익 {(TP_PCT - FEE['KR'])*100:.2f}%")
    print(f"  US 스윙 수수료: {FEE['US']*100:.2f}% (왕복) → TP 6%면 순수익 {(TP_PCT - FEE['US'])*100:.2f}%")
    print(f"  단타(15m) 수수료: KR {FEE['KR']*100:.2f}% → TP 2%면 순수익 {(0.02 - FEE['KR'])*100:.2f}%")
    print("=" * 65)

    # 결과 CSV 저장
    if rows:
        result_df = pd.DataFrame(rows)
        out_path = 'logs/swing_bt_result.csv'
        result_df.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"\n  결과 저장: {out_path}")


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
