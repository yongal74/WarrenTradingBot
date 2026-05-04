# -*- coding: utf-8 -*-
"""
Warren Paper Trading — V1
전략: 일봉 FVG + OB (스윙, 버그 수정)
==========================================
핵심 버그 3개 수정 (paper_base.py 공통 엔진에 구현):
  B1. 동일 zone 재진입 차단
  B2. 거래 중복 로깅 차단
  B3. 자본 회수 정확성 (open size = close size)

일봉 기준이므로 4시간마다 스캔.
스윙 보유 기간: 최대 20영업일.
"""
import pandas as pd
from paper_base import run_loop

VERSION = 'v1'

# ── 자본 설정 ────────────────────────────────────────────────
CONFIG = {
    'initial':       {'KR': 20_000_000, 'US': 20_000_000, 'CRYPTO': 10_000_000},
    'pos_size':      {'KR':  5_000_000, 'US':  5_000_000, 'CRYPTO':  3_000_000},
    'max_pos':       {'KR': 4,          'US': 4,           'CRYPTO': 3},
    'max_hold_days': 20,
    'loop_sec':      4 * 3600,   # 4시간마다 스캔
}

# ── 종목 유니버스 ────────────────────────────────────────────
# OB 0% WR 종목 제외: NVDA (OB만 제외, FVG는 추후 V2에서 검증)
UNIVERSE = {
    'KR': [
        ('005930', '삼성전자', '005930'),
        ('000270', '기아',     '000270'),
        ('068270', '셀트리온', '068270'),
        ('005380', '현대차',   '005380'),
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

# OB를 허용하지 않는 티커 (FVG만 허용)
_OB_BLACKLIST = {'NVDA', '034020'}

# ── 신호 감지: 일봉 FVG + OB ────────────────────────────────
SL_FLOOR = 0.010   # 1% 이상 SL만 유효 (스윙: 노이즈 제거)
SL_CAP   = 0.060   # 6% 이하 SL (스윙: 너무 넓은 구간 제외)
RR       = 2.0
ZONE_EXPIRE = 10   # 일봉 10봉 이내 미체결 시 무효


def detect_signal(df: pd.DataFrame, ticker: str) -> dict | None:
    """
    일봉 FVG 또는 OB 구간으로 가격이 되돌아왔을 때 신호 생성.
    Returns dict(type, zone_key, entry, sl, tp, sl_pct) or None.
    """
    n = len(df)
    zones = []

    # FVG (Fair Value Gap)
    for i in range(2, n - 1):
        hi2 = float(df['High'].iloc[i - 2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.003:   # 일봉: 0.3% 이상 갭
            zones.append({
                'type':      'FVG',
                'zone_key':  f"FVG_{hi2:.2f}_{lo0:.2f}",
                'zone_high': lo0,
                'zone_low':  hi2,
                'formed_i':  i,
                'expire_i':  i + ZONE_EXPIRE,
            })

    # OB (Order Block) — 블랙리스트 제외
    if ticker not in _OB_BLACKLIST:
        for i in range(1, n - 4):
            b = df.iloc[i]
            if float(b['Close']) >= float(b['Open']): continue
            imp = float(df['High'].iloc[i + 1:min(i + 4, n)].max())
            if (imp - float(b['High'])) / float(b['High']) > 0.010:   # 일봉: 1% 이상 충격파
                zones.append({
                    'type':      'OB',
                    'zone_key':  f"OB_{float(b['Low']):.2f}_{float(b['High']):.2f}",
                    'zone_high': float(b['High']),
                    'zone_low':  float(b['Low']),
                    'formed_i':  i,
                    'expire_i':  i + ZONE_EXPIRE,
                })

    last_i = n - 1
    active = [z for z in zones if z['formed_i'] < last_i <= z['expire_i']]
    cur_c  = float(df['Close'].iloc[-1])
    cur_l  = float(df['Low'].iloc[-1])

    # 최근 구간부터 확인
    for z in sorted(active, key=lambda x: x['formed_i'], reverse=True):
        zh, zl = z['zone_high'], z['zone_low']
        if cur_l <= zh and cur_c >= zl:        # 되돌림 진입 조건
            entry  = zh                         # 구간 상단 진입
            sl_pct = (entry - zl) / entry
            if not (SL_FLOOR <= sl_pct <= SL_CAP): continue
            return {
                'type':     z['type'],
                'zone_key': z['zone_key'],
                'entry':    round(entry, 4),
                'sl':       round(entry * (1 - sl_pct), 4),
                'tp':       round(entry * (1 + sl_pct * RR), 4),
                'sl_pct':   round(sl_pct * 100, 2),
            }
    return None


if __name__ == '__main__':
    run_loop(VERSION, CONFIG, UNIVERSE, detect_signal)
