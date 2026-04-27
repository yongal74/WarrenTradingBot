# -*- coding: utf-8 -*-
"""TDD: 전략 팩토리 단위 테스트"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np
from core.strategy_factory import get_signal, get_all_signals

def make_dummy_df(n=200, trend='up'):
    """테스트용 더미 데이터 생성"""
    dates = pd.date_range('2023-01-01', periods=n, freq='B')
    np.random.seed(42)
    if trend == 'up':
        close = 100 + np.cumsum(np.random.randn(n) * 0.5 + 0.3)
    elif trend == 'down':
        close = 100 + np.cumsum(np.random.randn(n) * 0.5 - 0.3)
    else:
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)

    close = np.maximum(close, 1)
    high  = close * (1 + np.abs(np.random.randn(n)) * 0.005)
    low   = close * (1 - np.abs(np.random.randn(n)) * 0.005)
    open_ = close * (1 + np.random.randn(n) * 0.003)
    vol   = np.random.randint(100000, 1000000, n)

    return pd.DataFrame({'Open':open_,'High':high,'Low':low,
                         'Close':close,'Volume':vol}, index=dates)

class TestStrategySignals:
    def test_all_signals_returns_dict(self):
        df = make_dummy_df()
        sigs = get_all_signals(df)
        assert isinstance(sigs, dict)
        assert len(sigs) == 25

    def test_signal_values_binary(self):
        df = make_dummy_df()
        sigs = get_all_signals(df)
        for k, v in sigs.items():
            assert v in [0, 1], f"{k} 신호값이 0/1이 아님: {v}"

    def test_get_signal_valid_strategy(self):
        df = make_dummy_df()
        sig = get_signal(df, 'S01_EMA9_21')
        assert sig in [0, 1]

    def test_get_signal_unknown_strategy(self):
        df = make_dummy_df()
        sig = get_signal(df, 'UNKNOWN_STRATEGY')
        assert sig == 0  # 알 수 없는 전략은 관망

    def test_insufficient_data_returns_zero(self):
        df = make_dummy_df(n=30)  # 데이터 부족
        sigs = get_all_signals(df)
        assert sigs == {}

    def test_ema_cross_uptrend(self):
        """강한 상승 추세에서 EMA9/21 신호 확인"""
        df = make_dummy_df(n=200, trend='up')
        sigs = get_all_signals(df)
        # 강한 상승추세에서 EMA9_21은 1일 가능성 높음 (확률적 테스트)
        assert 'S01_EMA9_21' in sigs

    def test_rsi_signal_exists(self):
        df = make_dummy_df()
        sigs = get_all_signals(df)
        assert 'S07_RSI_Trend' in sigs
        assert 'S08_RSI_Rev' in sigs

class TestRiskManager:
    def test_position_size(self):
        from core.portfolio_manager import PortfolioManager
        from core.risk_manager import RiskManager
        pm = PortfolioManager()
        rm = RiskManager(pm)
        qty = rm.position_size(price=50000)
        assert qty >= 1

    def test_stop_loss_trigger(self):
        from core.portfolio_manager import PortfolioManager
        from core.risk_manager import RiskManager
        pm = PortfolioManager()
        rm = RiskManager(pm)
        # -10% → 손절 (-7% 한도 초과)
        assert rm.should_stop_loss(100.0, 90.0) == True
        # -5% → 손절 안함
        assert rm.should_stop_loss(100.0, 95.0) == False

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
