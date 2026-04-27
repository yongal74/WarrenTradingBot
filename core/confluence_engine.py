# -*- coding: utf-8 -*-
"""
Confluence Engine — 5개 합류점 전략 + TP/SL 25% 로직

C1: DBB Smart Money    (DBB + FVG + MSB + VolBreak + Engulfing)
C2: Multi-Trend        (EMA9/21 + EMA20/50 + RSI + MACD + Ribbon)
C3: Breakout Confirm   (Donchian + ATR + BB상단 + Volume + GoldenX)
C4: Mean Reversion     (RSI역추세 + BB하단 + ZScore + SMA + PinBar)
C5: Pattern Structure  (CHoCH + InsideBar + Engulfing + FVG + Ichimoku)
"""
import warnings; warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_factory import _compute_all, _atr

# ── 최소 합류 점수 기준 ────────────────────────────────────────
MIN_SCORE = {
    'C1_DBB_SmartMoney':   4,   # 5개 중 4개
    'C2_MultiTrend':       4,   # 5개 중 4개
    'C3_Breakout':         3,   # 5개 중 3개 (돌파는 조건 맞추기 어려움)
    'C4_MeanReversion':    4,   # 5개 중 4개
    'C5_PatternStructure': 3,   # 5개 중 3개
}

CONFLUENCE_IDS = list(MIN_SCORE.keys())

TP_RATIO  = 0.25   # 익절: 전체 TP 거리의 25% 지점
ATR_SL    = 1.0    # 손절: 1x ATR
ATR_FULL_TP = 2.0  # 전체 TP 기준: 2x ATR


# ── DBB 구간 계산 ─────────────────────────────────────────────
def _dbb_zone(df: pd.DataFrame) -> pd.Series:
    """
    Double Bollinger Band 구간
    1  = Bull zone (종가 > 내부 상단 밴드 = 20MA + 1std)
    -1 = Bear zone (종가 < 내부 하단 밴드 = 20MA - 1std)
    0  = Neutral zone
    """
    c   = df['Close']
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    inner_upper = mid + 1 * std
    inner_lower = mid - 1 * std

    zone = pd.Series(0, index=df.index, dtype=int)
    zone[c > inner_upper] = 1
    zone[c < inner_lower] = -1
    return zone.shift(1).fillna(0)   # 전일 기준 (미래 참조 방지)


# ── 합류점 스코어 시리즈 계산 ──────────────────────────────────
def compute_score_series(df: pd.DataFrame) -> dict:
    """
    전체 DataFrame에 대해 C1~C5 합류 점수 시리즈 반환
    각 시리즈의 값: 0~5 (해당 날의 합류 신호 수)
    """
    if len(df) < 60:
        return {k: pd.Series(0, index=df.index) for k in CONFLUENCE_IDS}

    sigs = _compute_all(df)
    dbb  = _dbb_zone(df)

    c1 = (
        (dbb == 1).astype(int)    # DBB 강세 구간
        + sigs['S17_FVG']          # Fair Value Gap
        + sigs['S18_MSB']          # SR 플립 / 구조돌파
        + sigs['S22_VolBreak']     # 거래량 돌파
        + sigs['S21_Engulfing']    # 장악형 캔들
    )

    c2 = (
        sigs['S01_EMA9_21']        # 단기 추세
        + sigs['S02_EMA20_50']     # 중기 추세
        + sigs['S07_RSI_Trend']    # RSI 모멘텀
        + sigs['S09_MACD']         # MACD 크로스
        + sigs['S23_EMA_Ribbon']   # 장기 정배열
    )

    c3 = (
        sigs['S14_Donchian']       # 채널 돌파
        + sigs['S13_ATR_Break']    # ATR 변동성 돌파
        + sigs['S11_BB_Break']     # BB 상단 돌파
        + sigs['S22_VolBreak']     # 거래량 확인
        + sigs['S03_GoldenCross']  # 골든크로스 (매크로 필터)
    )

    c4 = (
        sigs['S08_RSI_Rev']        # RSI 과매도 반등
        + sigs['S12_BB_Rev']       # BB 하단 반등
        + sigs['S15_ZScore']       # 통계적 극단값
        + sigs['S16_SMA_Rev']      # SMA 이탈 회귀
        + sigs['S25_PinBar']       # 핀바 / 망치형 반전
    )

    c5 = (
        sigs['S24_CHoCH']          # 추세 캐릭터 전환
        + sigs['S20_InsideBar']    # Inside Bar 압축 → 돌파
        + sigs['S21_Engulfing']    # 장악형 캔들 확인
        + sigs['S17_FVG']          # FVG 불균형 구간
        + sigs['S06_Ichimoku']     # 일목균형표 클라우드 위
    )

    return {
        'C1_DBB_SmartMoney':   c1.clip(0, 5),
        'C2_MultiTrend':       c2.clip(0, 5),
        'C3_Breakout':         c3.clip(0, 5),
        'C4_MeanReversion':    c4.clip(0, 5),
        'C5_PatternStructure': c5.clip(0, 5),
    }


def get_latest_scores(df: pd.DataFrame) -> dict:
    """당일 합류 점수 딕셔너리 반환 {C1: 3, C2: 4, ...}"""
    series = compute_score_series(df)
    return {k: int(v.iloc[-1]) if len(v) > 0 and not pd.isna(v.iloc[-1]) else 0
            for k, v in series.items()}


def get_active_confluences(df: pd.DataFrame) -> list:
    """최소 점수 이상인 합류점 ID 목록 반환"""
    scores = get_latest_scores(df)
    return [k for k, v in scores.items() if v >= MIN_SCORE[k]]


# ── TP / SL 계산 ──────────────────────────────────────────────
def compute_tp_sl(entry: float, atr: float) -> dict:
    """
    ATR 기반 TP/SL 계산

    전체 구조:
      full_tp = entry + ATR * 2.0  (목표 저항까지)
      full_sl = entry - ATR * 1.0  (직전 지지 아래)

    실제 청산:
      actual_tp = entry + (full_tp - entry) * 0.25  ← TP 25% 지점
      actual_sl = full_sl                            ← SL은 그대로

    Args:
        entry: 진입가
        atr:   ATR(14) 값
    """
    full_tp_dist = atr * ATR_FULL_TP
    full_sl_dist = atr * ATR_SL

    full_tp  = entry + full_tp_dist
    full_sl  = entry - full_sl_dist
    actual_tp = entry + full_tp_dist * TP_RATIO
    actual_sl = full_sl

    return {
        'actual_tp':  round(actual_tp, 4),
        'actual_sl':  round(actual_sl, 4),
        'full_tp':    round(full_tp,   4),
        'full_sl':    round(full_sl,   4),
        'tp_pct':     round((actual_tp - entry) / entry * 100, 3),
        'sl_pct':     round((actual_sl - entry) / entry * 100, 3),
    }
