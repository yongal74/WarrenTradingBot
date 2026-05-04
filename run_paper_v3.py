# -*- coding: utf-8 -*-
"""
Warren Paper Trading — V3
전략: EMA 눌림목 매수 (Trend Pullback — 완전 신규)
====================================================
FVG/OB 개념 완전 탈피. 클래식 추세추종 스윙 전략.

진입 조건 (3단계):
  1. 장기 상승 추세: 종가 > EMA50
  2. 눌림목 발생:   최근 3봉 중 1봉 이상 EMA21 아래로 터치
  3. 반등 확인:     오늘 종가 > EMA21 (추세 회복)
  4. 거래량 확인:   오늘 거래량 > 20일 평균 거래량의 70%

손절: EMA50 하단 1% (장기 추세 이탈 기준)
목표: SL 거리 × 3 (R:R 1:3)

근거:
- 삼성 일봉 Momentum: 100% WR, +56,689원/trade (유일한 고수익 KR 전략)
- PLTR/AMD/SOXX 100% WR → 모두 상승 추세 종목
- 추세 추종 + 눌림목 = 가장 검증된 스윙 전략
"""
import pandas as pd
from paper_base import run_loop

VERSION = 'v3'

CONFIG = {
    'initial':       {'KR': 20_000_000, 'US': 20_000_000, 'CRYPTO': 10_000_000},
    'pos_size':      {'KR':  5_000_000, 'US':  5_000_000, 'CRYPTO':  3_000_000},
    'max_pos':       {'KR': 4,          'US': 4,           'CRYPTO': 3},
    'max_hold_days': 30,    # 스윙 30일 (추세 추종은 더 길게)
    'loop_sec':      4 * 3600,
}

# V3 유니버스: 상승 추세가 강한 종목 중심
# (FVG/OB 데이터에서 100% WR 종목 + 추세 명확 종목)
UNIVERSE = {
    'KR': [
        ('005930', '삼성전자', '005930'),
        ('000270', '기아',     '000270'),
        ('005380', '현대차',   '005380'),
        ('068270', '셀트리온', '068270'),
    ],
    'US': [
        ('AMD',  'AMD',      'AMD'),
        ('SOXX', '반도체ETF','SOXX'),
        ('PLTR', '팔란티어', 'PLTR'),
        ('TSLA', '테슬라',   'TSLA'),
    ],
    'CRYPTO': [
        ('BTC', '비트코인', 'KRW-BTC'),
        ('SOL', '솔라나',   'KRW-SOL'),
        ('ETH', '이더리움', 'KRW-ETH'),
        ('XRP', '리플',     'KRW-XRP'),
    ],
}

SL_FLOOR = 0.010   # EMA50 기반 SL 최소 1%
SL_CAP   = 0.080   # 최대 8% (스윙 허용)
RR       = 3.0     # R:R 1:3 (추세 추종은 더 큰 목표)


def detect_signal(df: pd.DataFrame, ticker: str) -> dict | None:
    """
    EMA 눌림목 반등 진입 신호.

    조건:
      1. close[-1] > EMA50[-1]          (장기 상승 추세)
      2. min(close[-4:-1]) < EMA21 해당 시점  (눌림목 발생)
      3. close[-1] > EMA21[-1]          (오늘 반등 확인)
      4. volume[-1] > vol_avg[-1] * 0.7 (거래량 최소 기준)
    """
    if len(df) < 55:
        return None

    close   = df['Close'].astype(float)
    high    = df['High'].astype(float)
    low     = df['Low'].astype(float)
    volume  = df['Volume'].astype(float)

    ema21   = close.ewm(span=21, adjust=False).mean()
    ema50   = close.ewm(span=50, adjust=False).mean()
    vol_avg = volume.rolling(20).mean()

    c_last  = close.iloc[-1]
    e21     = float(ema21.iloc[-1])
    e50     = float(ema50.iloc[-1])
    v_last  = float(volume.iloc[-1])
    v_avg   = float(vol_avg.iloc[-1])

    # 조건 1: 장기 상승 추세
    if c_last <= e50:
        return None

    # 조건 2: 최근 2~4봉 중 EMA21 하단 터치 (눌림목)
    pullback_occurred = False
    for i in range(-4, -1):
        if float(close.iloc[i]) < float(ema21.iloc[i]):
            pullback_occurred = True
            break
    if not pullback_occurred:
        return None

    # 조건 3: 오늘 종가 EMA21 위로 회복
    if c_last <= e21:
        return None

    # 조건 4: 거래량 기준 충족
    if v_avg > 0 and v_last < v_avg * 0.70:
        return None

    # 진입 / SL / TP 계산
    entry  = c_last                      # 현재 종가 = 내일 시가 근사
    sl     = e50 * 0.990                 # EMA50 하단 1% (추세 이탈 기준)
    sl_pct = (entry - sl) / entry

    if not (SL_FLOOR <= sl_pct <= SL_CAP):
        return None

    tp = entry + (entry - sl) * RR

    # zone_key: EMA21 레벨 기반 (같은 눌림목 구간 재진입 방지)
    zone_key = f"EMA21_{e21:.2f}"

    return {
        'type':     'EMA_PULLBACK',
        'zone_key': zone_key,
        'entry':    round(entry, 4),
        'sl':       round(sl, 4),
        'tp':       round(tp, 4),
        'sl_pct':   round(sl_pct * 100, 2),
    }


if __name__ == '__main__':
    run_loop(VERSION, CONFIG, UNIVERSE, detect_signal)
