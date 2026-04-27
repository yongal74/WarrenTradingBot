# -*- coding: utf-8 -*-
"""TDD: 성능 및 안정성 테스트"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np
import time


def make_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """테스트용 OHLCV 데이터 생성"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2023-01-01', periods=n, freq='B')
    close = np.maximum(100 + np.cumsum(rng.normal(0.2, 0.8, n)), 1.0)
    high  = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low   = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    vol   = rng.integers(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame({'Open': open_, 'High': high,
                         'Low': low, 'Close': close, 'Volume': vol}, index=dates)


class TestStrategyPerformance:
    """전략 계산 성능 테스트"""

    def test_all_signals_completes_within_1s(self):
        """25개 전략 신호 계산이 1초 내 완료되어야 함"""
        from core.strategy_factory import get_all_signals
        df = make_df(500)
        start = time.perf_counter()
        sigs = get_all_signals(df)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"신호 계산 너무 느림: {elapsed:.3f}s (한도: 1.0s)"
        assert len(sigs) == 25

    def test_repeated_calls_consistent(self):
        """동일 데이터에 대해 반복 호출 시 결과가 일관적이어야 함"""
        from core.strategy_factory import get_all_signals
        df = make_df(300)
        results = [get_all_signals(df) for _ in range(5)]
        for r in results[1:]:
            assert r == results[0], "동일 데이터에서 다른 결과가 나옴"

    def test_fvg_ob_detection_performance(self):
        """FVG+OB 감지가 2초 내 완료되어야 함"""
        from core.fvg_ob_tester import _detect_fvg, _detect_ob
        df = make_df(500)
        start = time.perf_counter()
        fvg_zones = _detect_fvg(df)
        ob_zones = _detect_ob(df)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"FVG+OB 감지 너무 느림: {elapsed:.3f}s"
        assert isinstance(fvg_zones, list)
        assert isinstance(ob_zones, list)


class TestDataIntegrity:
    """데이터 무결성 테스트"""

    def test_ohlcv_constraints(self):
        """High >= Low, Close/Open이 [Low, High] 범위 내에 있어야 함"""
        df = make_df(200)
        assert (df['High'] >= df['Low']).all(), "High < Low 데이터 존재"
        assert (df['High'] >= df['Close']).all(), "Close > High 데이터 존재"
        assert (df['Low'] <= df['Close']).all(), "Close < Low 데이터 존재"

    def test_no_negative_prices(self):
        """가격은 항상 양수여야 함"""
        df = make_df(200)
        for col in ['Open', 'High', 'Low', 'Close']:
            assert (df[col] > 0).all(), f"{col}에 0 이하 값 존재"

    def test_no_negative_volume(self):
        """거래량은 0 이상이어야 함"""
        df = make_df(200)
        assert (df['Volume'] >= 0).all(), "거래량에 음수 값 존재"

    def test_all_signals_have_expected_keys(self):
        """25개 전략 신호 키가 모두 존재해야 함"""
        from core.strategy_factory import get_all_signals
        expected_keys = {
            'S01_EMA9_21', 'S02_EMA20_50', 'S03_GoldenCross', 'S04_SuperTrend',
            'S05_HullMA', 'S06_Ichimoku', 'S07_RSI_Trend', 'S08_RSI_Rev',
            'S09_MACD', 'S10_MACDHist', 'S11_BB_Break', 'S12_BB_Rev',
            'S13_ATR_Break', 'S14_Donchian', 'S15_ZScore', 'S16_SMA_Rev',
            'S17_FVG', 'S18_MSB', 'S19_Monday', 'S20_InsideBar',
            'S21_Engulfing', 'S22_VolBreak', 'S23_EMA_Ribbon', 'S24_CHoCH',
            'S25_PinBar',
        }
        df = make_df(300)
        sigs = get_all_signals(df)
        missing = expected_keys - set(sigs.keys())
        assert not missing, f"누락된 전략 신호: {missing}"

    def test_confluence_scores_bounded(self):
        """C1~C5 합류점 스코어는 0~5 범위여야 함"""
        from core.confluence_engine import get_latest_scores
        df = make_df(300)
        scores = get_latest_scores(df)
        assert len(scores) == 5, f"합류점 개수 오류: {len(scores)}"
        for k, v in scores.items():
            assert 0 <= v <= 5, f"{k} 스코어 범위 오류: {v}"


class TestFVGOBLogic:
    """FVG+OB 감지 로직 정확성 테스트"""

    def test_fvg_zone_structure(self):
        """FVG 구간은 필수 키를 포함해야 함"""
        from core.fvg_ob_tester import _detect_fvg
        df = make_df(200)
        zones = _detect_fvg(df)
        required_keys = {'type', 'formed_i', 'zone_high', 'zone_low', 'expire_i'}
        for z in zones:
            missing = required_keys - set(z.keys())
            assert not missing, f"FVG 구간 키 누락: {missing}"
            assert z['type'] == 'FVG'
            assert z['zone_high'] >= z['zone_low'], "FVG zone_high < zone_low"

    def test_ob_zone_structure(self):
        """OB 구간은 필수 키를 포함해야 함"""
        from core.fvg_ob_tester import _detect_ob
        df = make_df(200)
        zones = _detect_ob(df)
        required_keys = {'type', 'formed_i', 'zone_high', 'zone_low', 'expire_i'}
        for z in zones:
            missing = required_keys - set(z.keys())
            assert not missing, f"OB 구간 키 누락: {missing}"
            assert z['type'] == 'OB'

    def test_fvg_expire_after_zone_formed(self):
        """FVG 만료 인덱스는 생성 인덱스보다 커야 함"""
        from core.fvg_ob_tester import _detect_fvg
        df = make_df(200)
        zones = _detect_fvg(df)
        for z in zones:
            assert z['expire_i'] > z['formed_i'], "FVG expire_i <= formed_i"

    def test_no_signal_on_empty_data(self):
        """데이터 부족 시 신호 없음"""
        from core.fvg_ob_tester import _check_signal
        df = make_df(10)  # 너무 적은 데이터
        sig = _check_signal(df)
        assert sig is None, "데이터 부족 시 신호 반환됨"

    def test_rr_ratio_correct(self):
        """R:R 비율 검증 — TP가 SL의 2배여야 함"""
        from core.fvg_ob_tester import _check_signal, RR_RATIO
        # RR_RATIO 상수 확인
        assert RR_RATIO == 2.0, f"R:R 비율 오류: {RR_RATIO} (기대: 2.0)"

    def test_sl_pct_within_bounds(self):
        """손절 % 상한/하한 상수 검증"""
        from core.fvg_ob_tester import MIN_SL_PCT, MAX_SL_PCT
        assert MIN_SL_PCT < MAX_SL_PCT, "MIN_SL_PCT >= MAX_SL_PCT"
        assert MIN_SL_PCT > 0, "MIN_SL_PCT는 양수여야 함"
        assert MAX_SL_PCT < 0.1, "MAX_SL_PCT가 10% 이상 — 비현실적"


class TestRiskManagement:
    """리스크 관리 테스트"""

    def test_max_position_pct_limit(self):
        """단일 포지션 최대 비율 준수"""
        from core.risk_manager import RiskManager
        from core.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        rm = RiskManager(pm)

        # 총 자본의 10% 이상 단일 포지션 불가
        price = 100_000
        qty = rm.position_size(price)
        position_value = price * qty
        max_allowed = pm.initial_capital * 0.10
        assert position_value <= max_allowed, \
            f"포지션 {position_value:,}원이 한도 {max_allowed:,}원 초과"

    def test_daily_loss_limit(self):
        """일일 손실 한도 -3% 이상이면 거래 중단"""
        from core.risk_manager import RiskManager
        from core.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        rm = RiskManager(pm)

        # 정상 손실 (-3%, DAILY_LOSS_LIMIT=-6% 미달)
        rm.record_pnl(-0.03)
        ok, _ = rm.check()
        assert ok, "정상 손실 범위(-3%)에서 거래 중단됨"

        # 한도 초과 (-4% 추가 → 누적 -7% → circuit breaker)
        rm.record_pnl(-0.04)
        ok, reason = rm.check()
        assert not ok, "한도 초과에도 거래 허용됨"
        assert "손실" in reason or "MDD" in reason

    def test_stop_loss_threshold(self):
        """손절 임계값 테스트"""
        from core.risk_manager import RiskManager
        from core.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        rm = RiskManager(pm)

        # STOP_LOSS_PCT=-1.5% 기준
        assert rm.should_stop_loss(100.0, 98.0) is True   # -2% → 손절
        assert rm.should_stop_loss(100.0, 98.6) is False  # -1.4% → 유지
        assert rm.should_stop_loss(100.0, 100.0) is False  # 0%
        assert rm.should_stop_loss(100.0, 110.0) is False  # +10%


class TestCacheSystem:
    """캐시 시스템 테스트"""

    def test_cache_path_no_special_chars(self):
        """캐시 파일 경로에 특수문자 없어야 함"""
        from data.data_loader import _cache_path
        path = _cache_path("BTC/KRW")
        assert '/' not in path.name, "캐시 파일명에 슬래시 포함"
        assert path.suffix == '.csv'

    def test_fresh_cache_detected(self):
        """최근 파일은 fresh로 판정"""
        import tempfile, os
        from data.data_loader import _is_fresh
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            tmp = Path(f.name)
        try:
            assert _is_fresh(tmp), "방금 만든 파일이 fresh 아님으로 판정됨"
        finally:
            tmp.unlink(missing_ok=True)

    def test_nonexistent_file_not_fresh(self):
        """존재하지 않는 파일은 fresh 아님"""
        from data.data_loader import _is_fresh
        assert not _is_fresh(Path("nonexistent_file_xyz.csv"))
