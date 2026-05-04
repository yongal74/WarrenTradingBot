# -*- coding: utf-8 -*-
"""
Warren Paper Trading — V2
전략: 일봉 FVG 전용 (스윙, 클린 버전)
==========================================
OB를 완전히 제거하고 FVG(Fair Value Gap)만 사용.
FVG는 기관 수요/공급 불균형 구간으로, 백테스트에서
OB(36% WR) 대비 훨씬 높은 성과를 보였음 (61.5% WR, PF 8.5).

추가 필터: DBB(Double Bollinger Band) Bull Zone
- 가격이 BB 상단 1σ 위에 있을 때만 진입 (Bull Zone)
- 약세 구간에서의 롱 진입 차단
"""
import pandas as pd
from paper_base import run_loop

VERSION = 'v2'

CONFIG = {
    'initial':       {'KR': 20_000_000, 'US': 20_000_000, 'CRYPTO': 10_000_000},
    'pos_size':      {'KR':  5_000_000, 'US':  5_000_000, 'CRYPTO':  3_000_000},
    'max_pos':       {'KR': 4,          'US': 4,           'CRYPTO': 3},
    'max_hold_days': 20,
    'loop_sec':      4 * 3600,
}

UNIVERSE = {
    'KR': [
        ('005930', '삼성전자', '005930'),
        ('000270', '기아',     '000270'),
        ('005380', '현대차',   '005380'),
        ('068270', '셀트리온', '068270'),
    ],
    'US': [
        ('TSLA', '테슬라',   'TSLA'),
        ('AMD',  'AMD',      'AMD'),
        ('SOXX', '반도체ETF','SOXX'),
        ('PLTR', '팔란티어', 'PLTR'),
    ],
    'CRYPTO': [
        ('BTC', '비트코인', 'KRW-BTC'),
        ('ETH', '이더리움', 'KRW-ETH'),
        ('SOL', '솔라나',   'KRW-SOL'),
        ('XRP', '리플',     'KRW-XRP'),
    ],
}

SL_FLOOR   = 0.010
SL_CAP     = 0.060
RR         = 2.0
ZONE_EXPIRE = 10


def _dbb_bull_zone(df: pd.DataFrame) -> bool:
    """DBB Bull Zone: 종가가 BB 중심선 + 1σ 위 여부."""
    if len(df) < 22:
        return True   # 데이터 부족 시 필터 비활성
    close = df['Close']
    mid   = close.rolling(20).mean()
    std   = close.rolling(20).std()
    upper1 = mid + std
    return float(close.iloc[-1]) > float(upper1.iloc[-1])


def detect_signal(df: pd.DataFrame, ticker: str) -> dict | None:
    """
    일봉 FVG 구간으로 되돌림 진입 신호.
    DBB Bull Zone 필터 추가 (Bear Zone 진입 차단).
    """
    n = len(df)
    zones = []

    for i in range(2, n - 1):
        hi2 = float(df['High'].iloc[i - 2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.003:
            zones.append({
                'type':      'FVG',
                'zone_key':  f"FVG_{hi2:.2f}_{lo0:.2f}",
                'zone_high': lo0,
                'zone_low':  hi2,
                'formed_i':  i,
                'expire_i':  i + ZONE_EXPIRE,
            })

    if not zones:
        return None

    # DBB Bull Zone 필터
    if not _dbb_bull_zone(df):
        return None

    last_i = n - 1
    active = [z for z in zones if z['formed_i'] < last_i <= z['expire_i']]
    cur_c  = float(df['Close'].iloc[-1])
    cur_l  = float(df['Low'].iloc[-1])

    for z in sorted(active, key=lambda x: x['formed_i'], reverse=True):
        zh, zl = z['zone_high'], z['zone_low']
        if cur_l <= zh and cur_c >= zl:
            entry  = zh
            sl_pct = (entry - zl) / entry
            if not (SL_FLOOR <= sl_pct <= SL_CAP): continue
            return {
                'type':     'FVG+DBB',
                'zone_key': z['zone_key'],
                'entry':    round(entry, 4),
                'sl':       round(entry * (1 - sl_pct), 4),
                'tp':       round(entry * (1 + sl_pct * RR), 4),
                'sl_pct':   round(sl_pct * 100, 2),
            }
    return None


if __name__ == '__main__':
    run_loop(VERSION, CONFIG, UNIVERSE, detect_signal)
