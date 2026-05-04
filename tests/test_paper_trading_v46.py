# -*- coding: utf-8 -*-
"""
TDD: Warren Paper Trading V4.6 신규 기능 단위 테스트
테스트 대상:
  - 화이트리스트 이중 방어선
  - TP 연장 전략 (_check_tp_extension)
  - 중복 거래 방지 (_is_duplicate_trade)
  - 전략 레지스트리 (_KR_STRATEGY_FN / _US_STRATEGY_FN)
  - KR 전략 배정 완성 (_KR_TICKER_STRATEGY)
  - POSITION_SIZE 재조정
  - BB반등 조건 강화 (RSI<60, BB1σ이하)
"""
import sys
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
import pandas as pd
import numpy as np


# ── 테스트 헬퍼 ──────────────────────────────────────────────────────

def make_ohlcv(n: int = 300, trend: str = 'up', seed: int = 42) -> pd.DataFrame:
    """테스트용 OHLCV 생성"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2023-01-01', periods=n, freq='B')
    drift = 0.3 if trend == 'up' else -0.3 if trend == 'down' else 0.0
    close = np.maximum(100 + np.cumsum(rng.normal(drift, 0.8, n)), 1.0)
    high  = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low   = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    vol   = rng.integers(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': vol},
        index=dates
    )


# ═══════════════════════════════════════════════════════════════════
# 1. 화이트리스트 이중 방어선 테스트
# ═══════════════════════════════════════════════════════════════════

class TestWhitelistGuard:
    """open_positions()의 하드 화이트리스트 검증"""

    def test_kr_universe_contains_correct_tickers(self):
        """KR 유니버스 16종목 포함 확인"""
        from core.fvg_ob_tester import KR_SWING_TICKERS
        expected = {
            '017670', '035720', '021240', '005380', '010140', '086790',
            '034020', '272210', '000660', '058470', '064350', '128940',
            '012450', '005930', '009150', '008060',
        }
        assert expected == set(KR_SWING_TICKERS.keys()), \
            f"KR 유니버스 불일치: {expected ^ set(KR_SWING_TICKERS.keys())}"

    def test_invalid_kr_tickers_not_in_universe(self):
        """퇴출 종목은 유니버스에 없어야 함"""
        from core.fvg_ob_tester import KR_SWING_TICKERS
        rejected = {'068270', '000270'}  # 셀트리온, 기아
        for t in rejected:
            assert t not in KR_SWING_TICKERS, f"{t}이 KR 유니버스에 남아있음"

    def test_invalid_us_tickers_not_in_universe(self):
        """PLTR, SOXX는 US 유니버스에 없어야 함"""
        from core.fvg_ob_tester import US_SWING_TICKERS
        rejected = {'PLTR', 'SOXX'}
        for t in rejected:
            assert t not in US_SWING_TICKERS, f"{t}이 US 유니버스에 남아있음"

    def test_crypto_universe_consistent(self):
        """CRYPTO 15m과 4H 유니버스 일관성 (BTC/ETH/SOL/XRP 공통)"""
        from core.fvg_ob_tester import CRYPTO_TICKERS, CRYPTO_4H_TICKERS
        core_set = {'BTC', 'ETH', 'SOL', 'XRP'}
        assert core_set == set(CRYPTO_TICKERS.keys()), "CRYPTO 15m 유니버스 불일치"
        assert core_set == set(CRYPTO_4H_TICKERS.keys()), "CRYPTO 4H 유니버스 불일치"


# ═══════════════════════════════════════════════════════════════════
# 2. 전략 레지스트리 테스트
# ═══════════════════════════════════════════════════════════════════

class TestStrategyRegistry:
    """KR/US 전략 레지스트리 완전성 검증"""

    def test_kr_strategy_registry_has_all_strategies(self):
        """KR 레지스트리에 5개 전략 모두 등록됨"""
        from core.fvg_ob_tester import _KR_STRATEGY_FN
        required = {'BB_SWING', 'MACD', 'SUPERTREND', 'GAPGO', 'MOMENTUM'}
        missing = required - set(_KR_STRATEGY_FN.keys())
        assert not missing, f"KR 전략 레지스트리 누락: {missing}"

    def test_us_strategy_registry_has_all_strategies(self):
        """US 레지스트리에 4개 전략 모두 등록됨"""
        from core.fvg_ob_tester import _US_STRATEGY_FN
        required = {'MACD', 'BB_REVERSAL', 'SUPERTREND', 'BB_MOM'}
        missing = required - set(_US_STRATEGY_FN.keys())
        assert not missing, f"US 전략 레지스트리 누락: {missing}"

    def test_kr_ticker_strategy_all_16_assigned(self):
        """KR 16종목 전략이 모두 배정됨"""
        from core.fvg_ob_tester import _KR_TICKER_STRATEGY, KR_SWING_TICKERS
        for code in KR_SWING_TICKERS:
            assert code in _KR_TICKER_STRATEGY, f"{code} 전략 미배정"

    def test_kr_ticker_strategy_values_valid(self):
        """KR 종목별 전략이 레지스트리에 존재하는 전략명이어야 함"""
        from core.fvg_ob_tester import _KR_TICKER_STRATEGY, _KR_STRATEGY_FN
        for code, strat in _KR_TICKER_STRATEGY.items():
            assert strat in _KR_STRATEGY_FN, \
                f"{code}의 전략 '{strat}'이 레지스트리에 없음"

    def test_us_ticker_strategy_values_valid(self):
        """US 종목별 전략이 레지스트리에 존재하는 전략명이어야 함"""
        from core.fvg_ob_tester import _US_TICKER_STRATEGY, _US_STRATEGY_FN
        for code, strat in _US_TICKER_STRATEGY.items():
            assert strat in _US_STRATEGY_FN, \
                f"{code}의 전략 '{strat}'이 레지스트리에 없음"

    def test_unknown_kr_strategy_returns_none(self):
        """레지스트리에 없는 KR 전략 조회 시 None 반환"""
        from core.fvg_ob_tester import _KR_STRATEGY_FN
        fn = _KR_STRATEGY_FN.get('NONEXISTENT_STRATEGY_XYZ')
        assert fn is None

    def test_kr_strategy_fn_callable(self):
        """KR 레지스트리의 모든 함수가 callable이어야 함"""
        from core.fvg_ob_tester import _KR_STRATEGY_FN
        for name, fn in _KR_STRATEGY_FN.items():
            assert callable(fn), f"{name} 전략 함수가 callable 아님"


# ═══════════════════════════════════════════════════════════════════
# 3. TP 연장 전략 테스트
# ═══════════════════════════════════════════════════════════════════

class TestTPExtension:
    """TP 연장 전략 (_check_tp_extension) 단위 테스트"""

    def _make_pos(self, tp_stage: int = 1, market: str = 'KR',
                  entry: float = 100_000, sl_pct: float = -2.0,
                  tp_pct: float = 4.0) -> dict:
        """테스트용 포지션 딕셔너리"""
        return {
            'ticker':    '005930',
            'name':      '삼성전자',
            'market':    market,
            'timeframe': 'daily',
            'entry':     entry,
            'sl':        entry * (1 + sl_pct / 100),
            'tp':        entry * (1 + tp_pct / 100),
            'sl_pct':    sl_pct,
            'tp_pct':    tp_pct,
            'tp_stage':  tp_stage,
            'size_krw':  5_000_000,
        }

    def test_tp3_returns_none_always(self):
        """TP3 단계 도달 시 연장 없이 None 반환"""
        from run_paper_trading import _check_tp_extension
        pos = self._make_pos(tp_stage=3)
        result = _check_tp_extension(pos, pos['tp'])
        assert result is None, "TP3 이후에도 연장이 허용됨"

    def test_extension_result_has_required_keys(self):
        """연장 성공 시 필수 키 포함"""
        from run_paper_trading import _check_tp_extension
        pos = self._make_pos(tp_stage=1)
        # yfinance 호출 없이 mock
        with patch('run_paper_trading.yf.download') as mock_dl, \
             patch('run_paper_trading._check_ema_align_15m', return_value=True), \
             patch('run_paper_trading._check_bearish_choch_15m', return_value=False), \
             patch('run_paper_trading._check_15m_rsi', return_value=True):
            # 일봉 데이터 mock (RSI < 75, MACD > Signal, 양봉)
            df = make_ohlcv(50, 'up')
            mock_dl.return_value = df
            result = _check_tp_extension(pos, pos['tp'] * 1.01)

        if result is not None:
            required_keys = {'new_tp', 'new_sl', 'stage', 'score', 'reason'}
            missing = required_keys - set(result.keys())
            assert not missing, f"TP 연장 결과 키 누락: {missing}"
            assert result['stage'] == 2, "TP1→TP2 전환 실패"
            assert result['new_sl'] > pos['sl'], "SL이 올라가지 않음"
            assert result['new_tp'] > pos['tp'], "TP가 올라가지 않음"

    def test_kr_after_close_no_extension(self):
        """KR 장 마감(15:20 이후) 연장 불가"""
        from run_paper_trading import _check_tp_extension
        pos = self._make_pos(tp_stage=1, market='KR')
        with patch('run_paper_trading.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 15
            mock_dt.now.return_value.minute = 25
            mock_dt.fromisoformat = __import__('datetime').datetime.fromisoformat
            result = _check_tp_extension(pos, pos['tp'])
        assert result is None, "장 마감 후 TP 연장 허용됨"

    def test_new_sl_equals_current_tp(self):
        """연장 시 새 SL = 현재 TP (수익 확보 원칙)"""
        from run_paper_trading import _check_tp_extension
        pos = self._make_pos(tp_stage=1)
        with patch('run_paper_trading.yf.download') as mock_dl, \
             patch('run_paper_trading._check_ema_align_15m', return_value=True), \
             patch('run_paper_trading._check_bearish_choch_15m', return_value=False), \
             patch('run_paper_trading._check_15m_rsi', return_value=True):
            df = make_ohlcv(50, 'up')
            mock_dl.return_value = df
            result = _check_tp_extension(pos, pos['tp'] * 1.01)

        if result is not None:
            assert abs(result['new_sl'] - pos['tp']) < 1.0, \
                f"새 SL({result['new_sl']})이 현재 TP({pos['tp']})와 다름"


# ═══════════════════════════════════════════════════════════════════
# 4. 중복 거래 방지 테스트
# ═══════════════════════════════════════════════════════════════════

class TestDuplicateTradeGuard:
    """_is_duplicate_trade() 중복 거래 방지"""

    def test_no_duplicate_on_empty_file(self):
        """CSV 없으면 중복 아님"""
        from run_paper_trading import _is_duplicate_trade
        with patch('run_paper_trading.TRADES_FILE') as mock_f:
            mock_f.exists.return_value = False
            assert not _is_duplicate_trade('NVDA', '2026-04-30 09:00:00')

    def test_duplicate_detected(self):
        """같은 (ticker, open_time) 조합이면 중복 감지"""
        import csv, io
        from run_paper_trading import _is_duplicate_trade

        csv_content = (
            "open_time,close_time,ticker\n"
            "2026-04-30 09:00:00,2026-04-30 10:00:00,NVDA\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                         delete=False, encoding='utf-8-sig') as f:
            f.write(csv_content)
            tmp_path = Path(f.name)
        try:
            with patch('run_paper_trading.TRADES_FILE', tmp_path):
                assert _is_duplicate_trade('NVDA', '2026-04-30 09:00:00')
                assert not _is_duplicate_trade('AMD', '2026-04-30 09:00:00')
                assert not _is_duplicate_trade('NVDA', '2026-04-30 11:00:00')
        finally:
            tmp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# 5. BB반등 조건 강화 테스트
# ═══════════════════════════════════════════════════════════════════

class TestBBSwingConditions:
    """BB반등 조건 강화 (RSI<60, BB1σ이하) 검증"""

    def test_rsi_threshold_60(self):
        """RSI >= 60이면 BB_SWING 신호 없어야 함"""
        from core.fvg_ob_tester import _check_swing_signal, _add_swing_indicators
        # RSI 높은 상승 추세 데이터
        df = make_ohlcv(300, trend='up', seed=0)
        result = _check_swing_signal(df, 'KR')
        # 강한 상승 추세에서는 RSI가 높아 신호 없어야 함
        if result is not None:
            assert result.get('rsi', 0) < 60, \
                f"RSI={result.get('rsi')}인데 BB_SWING 신호 발생 — RSI 조건 미작동"

    def test_min_entry_quality_4(self):
        """MIN_ENTRY_QUALITY == 4 확인"""
        from core.fvg_ob_tester import MIN_ENTRY_QUALITY
        assert MIN_ENTRY_QUALITY == 4, \
            f"MIN_ENTRY_QUALITY={MIN_ENTRY_QUALITY} (기대: 4)"

    def test_swing_sl_floor_2pct(self):
        """스윙 SL 최소값 2% 확인"""
        from core.fvg_ob_tester import SWING_SL_FLOOR
        assert abs(SWING_SL_FLOOR - 0.020) < 1e-9, \
            f"SWING_SL_FLOOR={SWING_SL_FLOOR} (기대: 0.020)"


# ═══════════════════════════════════════════════════════════════════
# 6. POSITION_SIZE 재조정 테스트
# ═══════════════════════════════════════════════════════════════════

class TestPositionSize:
    """포지션 사이즈 재조정 확인"""

    def test_kr_position_size_5m(self):
        """KR 포지션 크기 500만원"""
        from run_paper_trading import POSITION_SIZE
        assert POSITION_SIZE['KR'] == 5_000_000, \
            f"KR POSITION_SIZE={POSITION_SIZE['KR']:,} (기대: 5,000,000)"

    def test_us_position_size_10m(self):
        """US 포지션 크기 1,000만원"""
        from run_paper_trading import POSITION_SIZE
        assert POSITION_SIZE['US'] == 10_000_000, \
            f"US POSITION_SIZE={POSITION_SIZE['US']:,} (기대: 10,000,000)"

    def test_crypto_position_size_5m(self):
        """CRYPTO 포지션 크기 500만원"""
        from run_paper_trading import POSITION_SIZE
        assert POSITION_SIZE['CRYPTO'] == 5_000_000, \
            f"CRYPTO POSITION_SIZE={POSITION_SIZE['CRYPTO']:,} (기대: 5,000,000)"

    def test_position_size_within_capital_limit(self):
        """포지션 크기가 초기자본의 25% 이하 (최대 5포지션 기준)"""
        from run_paper_trading import POSITION_SIZE, INITIAL_CAPITAL, MAX_POS_PER_MARKET
        for mkt in ['KR', 'US', 'CRYPTO']:
            ps  = POSITION_SIZE[mkt]
            cap = INITIAL_CAPITAL[mkt]
            max_pos = MAX_POS_PER_MARKET[mkt]
            total_exposure = ps * max_pos
            assert total_exposure <= cap, \
                f"{mkt}: {max_pos}포지션 총 {total_exposure:,}원이 자본 {cap:,}원 초과"


# ═══════════════════════════════════════════════════════════════════
# 7. config/assets.py 동기화 테스트
# ═══════════════════════════════════════════════════════════════════

class TestAssetsSync:
    """config/assets.py와 fvg_ob_tester.py 유니버스 동기화 확인"""

    def test_kr_assets_matches_swing_tickers(self):
        """config KR_ASSETS == fvg_ob_tester KR_SWING_TICKERS"""
        from config.assets import KR_ASSETS
        from core.fvg_ob_tester import KR_SWING_TICKERS
        assert set(KR_ASSETS.keys()) == set(KR_SWING_TICKERS.keys()), \
            f"KR 유니버스 불일치: {set(KR_ASSETS.keys()) ^ set(KR_SWING_TICKERS.keys())}"

    def test_us_assets_matches_swing_tickers(self):
        """config US_ASSETS == fvg_ob_tester US_SWING_TICKERS"""
        from config.assets import US_ASSETS
        from core.fvg_ob_tester import US_SWING_TICKERS
        assert set(US_ASSETS.keys()) == set(US_SWING_TICKERS.keys()), \
            f"US 유니버스 불일치: {set(US_ASSETS.keys()) ^ set(US_SWING_TICKERS.keys())}"

    def test_no_pltr_in_us_assets(self):
        """PLTR은 US_ASSETS에 없어야 함"""
        from config.assets import US_ASSETS
        assert 'PLTR' not in US_ASSETS

    def test_no_soxx_in_us_assets(self):
        """SOXX는 US_ASSETS에 없어야 함"""
        from config.assets import US_ASSETS
        assert 'SOXX' not in US_ASSETS

    def test_all_assets_have_strategy(self):
        """모든 종목에 strategy 필드 있어야 함"""
        from config.assets import ALL_ASSETS
        for ticker, info in ALL_ASSETS.items():
            assert 'strategy' in info, f"{ticker}에 strategy 필드 없음"
            assert info['strategy'], f"{ticker} strategy 값이 비어있음"


# ═══════════════════════════════════════════════════════════════════
# 8. 포트폴리오 저장 자동 갱신 테스트
# ═══════════════════════════════════════════════════════════════════

class TestPortfolioSave:
    """_save_portfolio() win_rate_pct 자동 갱신"""

    def test_win_rate_auto_calculated(self):
        """저장 시 win_rate_pct 자동 계산"""
        from run_paper_trading import _save_portfolio

        port = {
            'total_trades': 10,
            'wins': 6,
            'losses': 4,
            'realized_pnl': {'KR': 100000, 'US': 200000, 'CRYPTO': -50000},
            'history': [],
        }
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = Path(f.name)
        try:
            with patch('run_paper_trading.PORT_FILE', tmp):
                _save_portfolio(port)
            assert port['win_rate_pct'] == 60.0, \
                f"win_rate_pct={port.get('win_rate_pct')} (기대: 60.0)"
        finally:
            tmp.unlink(missing_ok=True)

    def test_total_realized_krw_auto_calculated(self):
        """저장 시 total_realized_krw 자동 합산"""
        from run_paper_trading import _save_portfolio

        port = {
            'total_trades': 5,
            'wins': 3,
            'losses': 2,
            'realized_pnl': {'KR': 100_000, 'US': 200_000, 'CRYPTO': -50_000},
            'history': [],
        }
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = Path(f.name)
        try:
            with patch('run_paper_trading.PORT_FILE', tmp):
                _save_portfolio(port)
            assert port['total_realized_krw'] == 250_000, \
                f"total_realized_krw={port.get('total_realized_krw')} (기대: 250000)"
        finally:
            tmp.unlink(missing_ok=True)

    def test_zero_trades_no_division_error(self):
        """거래 0건일 때 0 나누기 오류 없음"""
        from run_paper_trading import _save_portfolio

        port = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0},
            'history': [],
        }
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = Path(f.name)
        try:
            with patch('run_paper_trading.PORT_FILE', tmp):
                _save_portfolio(port)
            assert port['win_rate_pct'] == 0
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
