# -*- coding: utf-8 -*-
"""
Step 2 — v5.2 ATR 기반 포지션 사이징 단위 테스트

테스트 대상:
  _get_atr()                   — ATR% 계산 (yfinance 모킹)
  calc_risk_based_position_size() — SL/ATR 기반 포지션 계산 (dict 반환)

핵심 공식:
  risk_krw     = total_equity * risk_pct
  sl_based_krw = risk_krw / sl_pct
  atr_based_krw= risk_krw / atr_pct
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ════════════════════════════════════════════════════════════════════
# calc_risk_based_position_size — 반환 타입 및 기본 공식
# ════════════════════════════════════════════════════════════════════

class TestCalcRiskBasedPositionSizeV52:
    """v5.2: dict 반환 + ATR 지원"""

    def test_returns_dict(self):
        from run_paper_trading import calc_risk_based_position_size
        result = calc_risk_based_position_size(200_000_000, 100.0, 98.0)
        assert isinstance(result, dict)
        assert 'sl_based_krw'   in result
        assert 'atr_based_krw'  in result
        assert 'recommended_krw' in result
        assert 'risk_krw'       in result
        assert 'sl_pct'         in result
        assert 'atr_pct_used'   in result

    def test_sl_based_formula(self):
        """2억 × 0.3% / 2% = 3,000만"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=98.0, risk_pct=0.003)
        assert r['risk_krw'] == 600_000                       # 2억 × 0.3%
        assert r['sl_pct']   == pytest.approx(2.0, rel=0.01)  # (100-98)/100
        assert r['sl_based_krw'] == pytest.approx(30_000_000, rel=0.01)  # 60만/2%

    def test_atr_based_formula(self):
        """ATR=3% → 3,000만 / ATR=6% → 1,000만"""
        from run_paper_trading import calc_risk_based_position_size
        r3 = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=98.0,
            risk_pct=0.003, atr_pct=0.03)
        r6 = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=98.0,
            risk_pct=0.003, atr_pct=0.06)
        assert r3['atr_based_krw'] == pytest.approx(20_000_000, rel=0.01)  # 60만/3%
        assert r6['atr_based_krw'] == pytest.approx(10_000_000, rel=0.01)  # 60만/6%

    def test_higher_volatility_smaller_position(self):
        """변동성 높을수록 포지션 작아짐"""
        from run_paper_trading import calc_risk_based_position_size
        low_vol  = calc_risk_based_position_size(200_000_000, 100.0, 99.0, atr_pct=0.01)
        high_vol = calc_risk_based_position_size(200_000_000, 100.0, 99.0, atr_pct=0.05)
        assert low_vol['atr_based_krw'] > high_vol['atr_based_krw']

    def test_recommended_is_atr_when_available(self):
        """ATR 있으면 recommended_krw = atr_based_krw"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=97.0,
            risk_pct=0.003, atr_pct=0.04)
        assert r['recommended_krw'] == r['atr_based_krw']

    def test_recommended_is_sl_when_no_atr(self):
        """ATR 없으면 recommended_krw = sl_based_krw"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=97.0, risk_pct=0.003)
        assert r['recommended_krw'] == r['sl_based_krw']
        assert r['atr_based_krw']   == 0

    def test_max_cap_applies_to_both(self):
        """max_position_krw가 SL기반/ATR기반 양쪽에 적용됨"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000, entry_price=100.0, sl_price=99.9,
            risk_pct=0.003, max_position_krw=10_000_000, atr_pct=0.001)
        assert r['sl_based_krw']  <= 10_000_000
        assert r['atr_based_krw'] <= 10_000_000

    def test_zero_sl_returns_zero_sl_based(self):
        """SL=Entry → sl_based_krw=0 (division by zero 방지)"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(200_000_000, 100.0, 100.0)
        assert r['sl_based_krw'] == 0

    def test_risk_krw_calculation(self):
        """risk_krw = total_equity × risk_pct"""
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=100_000_000, entry_price=50.0, sl_price=49.0, risk_pct=0.005)
        assert r['risk_krw'] == 500_000  # 1억 × 0.5%

    def test_real_example_nvda(self):
        """
        실전 예: NVDA
        - total_equity = 2억
        - risk_pct = 0.3% → risk_krw = 60만
        - entry=200, sl=196 → sl_pct=2% → sl_based=3,000만
        - ATR 3일선 약 3% → atr_based=2,000만
        → 고정(1,000만)보다 크지만 변동성 반영
        """
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000,
            entry_price=200.0,
            sl_price=196.0,       # -2%
            risk_pct=0.003,
            atr_pct=0.03,         # 3%
        )
        assert r['sl_based_krw']  == pytest.approx(30_000_000, rel=0.01)
        assert r['atr_based_krw'] == pytest.approx(20_000_000, rel=0.01)
        assert r['recommended_krw'] == r['atr_based_krw']


# ════════════════════════════════════════════════════════════════════
# _get_atr() — yfinance 모킹 기반 ATR 계산
# ════════════════════════════════════════════════════════════════════

def _make_ohlcv(n: int = 30, base: float = 100.0, volatility: float = 2.0) -> pd.DataFrame:
    """테스트용 일봉 OHLCV 데이터 생성"""
    rng = np.random.default_rng(42)
    closes = base + np.cumsum(rng.normal(0, 1, n))
    highs  = closes + rng.uniform(0.5, volatility, n)
    lows   = closes - rng.uniform(0.5, volatility, n)
    opens  = closes + rng.normal(0, 0.3, n)
    df = pd.DataFrame({'Open': opens, 'High': highs, 'Low': lows, 'Close': closes,
                       'Volume': rng.integers(100_000, 1_000_000, n)})
    df.index = pd.date_range('2026-01-01', periods=n, freq='B')
    return df


class TestGetAtr:
    def test_returns_float_when_data_available(self):
        """데이터 충분하면 float 반환"""
        import run_paper_trading as rpt
        mock_df = _make_ohlcv(30, base=100.0, volatility=2.0)

        with patch('yfinance.download', return_value=mock_df), \
             patch.dict(rpt.YF_TICKER, {'AMD': 'AMD'}):
            result = rpt._get_atr('AMD', market='US')

        assert result is not None
        assert isinstance(result, float)
        assert 0.0 < result < 1.0    # ATR%는 0~100% 사이

    def test_higher_volatility_higher_atr(self):
        """변동성 높은 종목이 ATR% 더 큼"""
        import run_paper_trading as rpt
        low_vol_df  = _make_ohlcv(30, base=100.0, volatility=0.5)
        high_vol_df = _make_ohlcv(30, base=100.0, volatility=5.0)

        with patch.dict(rpt.YF_TICKER, {'TICK_LOW': 'TICK_LOW', 'TICK_HIGH': 'TICK_HIGH'}):
            with patch('yfinance.download', return_value=low_vol_df):
                atr_low = rpt._get_atr('TICK_LOW', market='US')
            with patch('yfinance.download', return_value=high_vol_df):
                atr_high = rpt._get_atr('TICK_HIGH', market='US')

        assert atr_high > atr_low

    def test_returns_none_on_insufficient_data(self):
        """데이터 부족 시 None 반환"""
        import run_paper_trading as rpt
        short_df = _make_ohlcv(5)   # 14봉 미만 → None

        with patch('yfinance.download', return_value=short_df), \
             patch.dict(rpt.YF_TICKER, {'SHORTTICK': 'SHORTTICK'}):
            result = rpt._get_atr('SHORTTICK', market='US')

        assert result is None

    def test_returns_none_for_unknown_ticker(self):
        """YF_TICKER에 없는 종목 → None"""
        import run_paper_trading as rpt
        result = rpt._get_atr('UNKNOWN_TICKER_XYZ', market='US')
        assert result is None

    def test_atr_pct_reasonable_range(self):
        """실전 종목 ATR%는 보통 0.5%~8% 범위"""
        import run_paper_trading as rpt
        # 기준가 200, 일평균 변동 약 3 → ATR% ≈ 1.5%
        df = _make_ohlcv(30, base=200.0, volatility=3.0)

        with patch('yfinance.download', return_value=df), \
             patch.dict(rpt.YF_TICKER, {'TEST': 'TEST'}):
            atr = rpt._get_atr('TEST', market='US')

        assert atr is not None
        assert 0.001 < atr < 0.15   # 0.1% ~ 15% 범위


# ════════════════════════════════════════════════════════════════════
# 통합: SL < ATR 비교 시나리오
# ════════════════════════════════════════════════════════════════════

class TestSizingComparison:
    def test_low_sl_high_atr_scenario(self):
        """
        SL이 좁고 ATR이 넓을 때:
        - SL 1% → sl_based = 6,000만 (큼)
        - ATR 5% → atr_based = 1,200만 (작음)
        → ATR 기반이 더 보수적 → recommended = atr_based
        """
        from run_paper_trading import calc_risk_based_position_size
        r = calc_risk_based_position_size(
            total_equity=200_000_000,
            entry_price=100.0, sl_price=99.0,   # SL 1%
            risk_pct=0.003, atr_pct=0.05)        # ATR 5%
        assert r['sl_based_krw']  > r['atr_based_krw']    # SL기반 > ATR기반
        assert r['recommended_krw'] == r['atr_based_krw']  # 더 작은 쪽 권장

    def test_fixed_vs_recommended_comparison(self):
        """
        고정 포지션(1,000만)과 권장 포지션 비교 로그 시나리오:
        변동성 낮은 종목 → 권장이 고정보다 클 수 있음
        변동성 높은 종목 → 권장이 고정보다 작을 수 있음
        """
        from run_paper_trading import calc_risk_based_position_size
        FIXED_US = 10_000_000

        # 변동성 낮음 (ATR 1%) → 권장 > 고정
        low_vol = calc_risk_based_position_size(
            200_000_000, 100.0, 99.0, risk_pct=0.003, atr_pct=0.01)
        assert low_vol['recommended_krw'] > FIXED_US   # 60만/1% = 6,000만 > 1,000만

        # 변동성 높음 (ATR 8%) → 권장 < 고정
        high_vol = calc_risk_based_position_size(
            200_000_000, 100.0, 99.0, risk_pct=0.003, atr_pct=0.08)
        assert high_vol['recommended_krw'] < FIXED_US  # 60만/8% = 750만 < 1,000만


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
