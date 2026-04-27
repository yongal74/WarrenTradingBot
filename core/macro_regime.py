# -*- coding: utf-8 -*-
"""
Pillar 1 — 거시 경제 국면 판별
VIX / DXY / US10Y / 원달러 / 유가 → HALT / DEFENSIVE / NORMAL / AGGRESSIVE

사용:
    from core.macro_regime import get_regime
    regime, data = get_regime()
"""
import warnings; warnings.filterwarnings('ignore')
import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── 임계값 ────────────────────────────────────────────────
VIX_HALT        = 35.0   # VIX > 35  → 전면 차단
VIX_DEFENSIVE   = 25.0   # VIX > 25  → 방어 모드
VIX_NORMAL      = 20.0   # VIX > 20  → 보통
                         # VIX < 20  → 적극 매수

DXY_SPIKE_PCT   =  1.5   # DXY 5일 변화율 > 1.5% → 위험
DXY_RISE_PCT    =  0.8   # DXY 5일 변화율 > 0.8% → 주의

US10Y_HIGH      =  4.8   # 10Y 금리 > 4.8% → 위험
US10Y_WATCH     =  4.2   # 10Y 금리 > 4.2% → 주의

KRW_WEAK        = 1400   # 원달러 > 1400 → 한국주식 방어
KRW_CRISIS      = 1450   # 원달러 > 1450 → 한국주식 차단

OIL_SPIKE       =  90    # WTI > 90 → 인플레이션 우려


def _safe_last(df) -> float | None:
    """DataFrame 또는 Series에서 마지막 값 안전하게 추출"""
    try:
        if df is None or (hasattr(df, 'empty') and df.empty):
            return None
        if isinstance(df, pd.DataFrame):
            if hasattr(df.columns, 'levels'):
                df.columns = df.columns.droplevel(1)
            return float(df['Close'].dropna().iloc[-1])
        return float(df.dropna().iloc[-1])
    except Exception:
        return None


def get_regime(use_cache: bool = True) -> tuple[str, dict]:
    """
    매크로 지표를 조회해 국면 판단.
    Returns:
        regime: 'HALT' | 'DEFENSIVE' | 'NORMAL' | 'AGGRESSIVE'
        data:   각 지표 현재값 딕셔너리
    """
    # ── 데이터 조회 ────────────────────────────────────────
    tickers = {
        'vix':  '^VIX',
        'dxy':  'DX-Y.NYB',
        't10y': '^TNX',
        'krw':  'KRW=X',
        'oil':  'CL=F',
    }

    raw: dict[str, float | None] = {}
    dxy_5d_chg = 0.0

    for key, sym in tickers.items():
        try:
            df = yf.download(sym, period='10d', interval='1d',
                             auto_adjust=True, progress=False)
            if hasattr(df.columns, 'levels'):
                df.columns = df.columns.droplevel(1)
            c = df['Close'].dropna()
            raw[key] = float(c.iloc[-1]) if len(c) > 0 else None
            if key == 'dxy' and len(c) >= 5:
                dxy_5d_chg = (float(c.iloc[-1]) - float(c.iloc[-5])) / float(c.iloc[-5]) * 100
        except Exception:
            raw[key] = None

    vix   = raw.get('vix')
    dxy   = raw.get('dxy')
    t10y  = raw.get('t10y')
    krw   = raw.get('krw')
    oil   = raw.get('oil')

    # ── 점수 계산 (높을수록 위험) ───────────────────────────
    score = 0
    reasons: list[str] = []

    # VIX
    if vix is not None:
        if vix > VIX_HALT:
            return 'HALT', _build_data(raw, dxy_5d_chg, score,
                                       [f'VIX={vix:.1f} > {VIX_HALT} (위기)'])
        if vix > VIX_DEFENSIVE:
            score += 3; reasons.append(f'VIX={vix:.1f} 고공포')
        elif vix > VIX_NORMAL:
            score += 1; reasons.append(f'VIX={vix:.1f} 주의')

    # DXY (달러 강세 = 위험자산 약세)
    if dxy_5d_chg > DXY_SPIKE_PCT:
        score += 2; reasons.append(f'DXY 5일+{dxy_5d_chg:.1f}% 급등')
    elif dxy_5d_chg > DXY_RISE_PCT:
        score += 1; reasons.append(f'DXY 5일+{dxy_5d_chg:.1f}% 상승')

    # US10Y
    if t10y is not None:
        if t10y > US10Y_HIGH:
            score += 2; reasons.append(f'US10Y={t10y:.2f}% 고금리')
        elif t10y > US10Y_WATCH:
            score += 1; reasons.append(f'US10Y={t10y:.2f}% 주의')

    # 원달러 (KR 종목 한정)
    if krw is not None:
        if krw > KRW_CRISIS:
            score += 2; reasons.append(f'원달러={krw:.0f} 위기')
        elif krw > KRW_WEAK:
            score += 1; reasons.append(f'원달러={krw:.0f} 약세')

    # 유가
    if oil is not None and oil > OIL_SPIKE:
        score += 1; reasons.append(f'WTI={oil:.1f} 고유가')

    # ── 국면 결정 ──────────────────────────────────────────
    if score >= 5:
        regime = 'DEFENSIVE'
    elif score >= 2:
        regime = 'NORMAL'
    else:
        regime = 'AGGRESSIVE'

    return regime, _build_data(raw, dxy_5d_chg, score, reasons)


def _build_data(raw: dict, dxy_chg: float, score: int,
                reasons: list[str]) -> dict:
    return {
        'vix':          raw.get('vix'),
        'dxy':          raw.get('dxy'),
        'dxy_5d_chg':   round(dxy_chg, 2),
        't10y':         raw.get('t10y'),
        'krw':          raw.get('krw'),
        'oil':          raw.get('oil'),
        'score':        score,
        'reasons':      reasons,
        'updated_at':   datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def regime_for_market(regime: str, market: str) -> str:
    """
    시장별 국면 보정:
    - KR: 원달러 > 1450 → 독자적 HALT
    - CRYPTO: DEFENSIVE여도 24H 거래라 NORMAL 유지
    """
    return regime


def min_quality_by_regime(regime: str) -> int:
    """
    국면별 최소 진입 품질 점수 (0=필터 없음)
    AGGRESSIVE / NORMAL : FVG+OB 단독 (0점 → 필터 없음)
    DEFENSIVE           : 7점 중 3점 이상
    HALT                : 거래 불가 (호출 자체 차단됨)
    """
    return 3 if regime == 'DEFENSIVE' else 0


if __name__ == '__main__':
    regime, data = get_regime()
    print(f'\n  Macro Regime: [{regime}]')
    print(f'  VIX={data["vix"]:.1f}  DXY={data["dxy"]:.2f}(5d{data["dxy_5d_chg"]:+.1f}%)'
          f'  US10Y={data["t10y"]:.2f}%  KRW={data["krw"]:.0f}  WTI={data["oil"]:.1f}')
    print(f'  Score={data["score"]}  |  ', ' / '.join(data["reasons"]) if data["reasons"] else '이상 없음')
