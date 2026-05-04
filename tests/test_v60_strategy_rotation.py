# -*- coding: utf-8 -*-
"""
Step 4 — v6.0 전략 로테이션 단위 테스트

테스트 대상:
  _detect_market_regime()       — TRENDING / SIDEWAYS / RISK_OFF 판정
  _generate_rotation_proposal() — PENDING 제안 생성 (자동 적용 금지 확인)
  ROTATION_STRATEGY 구조        — 레짐별 전략 우선순위 키 검증
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 헬퍼: yfinance 목 데이터 생성
# ═══════════════════════════════════════════════════════════════════

def _make_price_df(n: int, base: float = 400.0) -> pd.DataFrame:
    """단순 가격 DataFrame (Close만 사용)"""
    rng = np.random.default_rng(42)
    closes = base + np.cumsum(rng.normal(0, 2, n))
    df = pd.DataFrame({
        'Open': closes, 'High': closes + 1, 'Low': closes - 1,
        'Close': closes, 'Volume': 1_000_000,
    })
    df.index = pd.date_range('2025-01-01', periods=n, freq='B')
    return df


def _make_vix_df(vix_value: float) -> pd.DataFrame:
    df = pd.DataFrame({'Close': [vix_value]},
                      index=pd.date_range('2026-05-01', periods=1, freq='B'))
    df['Open'] = vix_value
    df['High'] = vix_value
    df['Low']  = vix_value
    df['Volume'] = 0
    return df


# ═══════════════════════════════════════════════════════════════════
# TestRotationStrategyStructure — ROTATION_STRATEGY 구조 검증
# ═══════════════════════════════════════════════════════════════════

class TestRotationStrategyStructure:

    def test_all_regimes_exist(self):
        """TRENDING / SIDEWAYS / RISK_OFF 키 존재"""
        from run_paper_trading import ROTATION_STRATEGY
        assert 'TRENDING'  in ROTATION_STRATEGY
        assert 'SIDEWAYS'  in ROTATION_STRATEGY
        assert 'RISK_OFF'  in ROTATION_STRATEGY

    def test_each_regime_has_markets(self):
        """각 레짐에 US/KR/CRYPTO/reason 키 존재"""
        from run_paper_trading import ROTATION_STRATEGY
        for regime, data in ROTATION_STRATEGY.items():
            assert 'US'     in data, f"{regime} missing US"
            assert 'KR'     in data, f"{regime} missing KR"
            assert 'CRYPTO' in data, f"{regime} missing CRYPTO"
            assert 'reason' in data, f"{regime} missing reason"

    def test_strategy_lists_are_lists(self):
        """전략 목록이 list 타입"""
        from run_paper_trading import ROTATION_STRATEGY
        for regime, data in ROTATION_STRATEGY.items():
            assert isinstance(data['US'], list)
            assert isinstance(data['KR'], list)
            assert isinstance(data['CRYPTO'], list)

    def test_risk_off_crypto_empty(self):
        """RISK_OFF 시 CRYPTO 목록은 빈 리스트 (신규 진입 자제)"""
        from run_paper_trading import ROTATION_STRATEGY
        assert ROTATION_STRATEGY['RISK_OFF']['CRYPTO'] == []

    def test_trending_first_strategy(self):
        """TRENDING 시 US 첫 전략은 MACD (모멘텀)"""
        from run_paper_trading import ROTATION_STRATEGY
        assert ROTATION_STRATEGY['TRENDING']['US'][0] == 'MACD'

    def test_sideways_first_strategy(self):
        """SIDEWAYS 시 US 첫 전략은 BB_REVERSAL (평균회귀)"""
        from run_paper_trading import ROTATION_STRATEGY
        assert ROTATION_STRATEGY['SIDEWAYS']['US'][0] == 'BB_REVERSAL'


# ═══════════════════════════════════════════════════════════════════
# TestDetectMarketRegime — 레짐 판정 로직
# ═══════════════════════════════════════════════════════════════════

class TestDetectMarketRegime:

    def _mock_download(self, spy_vs_200, qqq_slope_positive, vix_value):
        """SPY/QQQ/VIX 목 데이터 반환 함수 생성"""
        spy_df  = _make_price_df(220, base=400.0)
        # SPY 200MA 조작: 현재가 = 200MA * (1 + spy_vs_200/100)
        ma200 = float(spy_df['Close'].rolling(200).mean().iloc[-1])
        target_price = ma200 * (1 + spy_vs_200 / 100)
        spy_df['Close'].iloc[-1] = target_price
        spy_df['Open'].iloc[-1]  = target_price
        spy_df['High'].iloc[-1]  = target_price
        spy_df['Low'].iloc[-1]   = target_price

        qqq_df = _make_price_df(70, base=350.0)
        if not qqq_slope_positive:
            # 50MA 하락: 최근 6봉 가격 낮추기
            qqq_df['Close'].iloc[-6:] -= 20
        vix_df = _make_vix_df(vix_value)
        return spy_df, qqq_df, vix_df

    def test_trending_regime(self):
        """SPY 200MA +5%, QQQ 상향, VIX=15 → TRENDING"""
        import run_paper_trading as rpt
        spy_df, qqq_df, vix_df = self._mock_download(
            spy_vs_200=5.0, qqq_slope_positive=True, vix_value=15.0
        )
        call_map = {'SPY': spy_df, 'QQQ': qqq_df, '^VIX': vix_df}

        def fake_download(ticker, **kwargs):
            return call_map.get(ticker, _make_price_df(10))

        with patch('yfinance.download', side_effect=fake_download):
            result = rpt._detect_market_regime()

        assert result['regime'] == 'TRENDING'
        assert 'spy_vs_200ma' in result
        assert 'vix_level'    in result

    def test_risk_off_vix(self):
        """VIX=35 → RISK_OFF (VIX 기준 우선)"""
        import run_paper_trading as rpt
        spy_df, qqq_df, vix_df = self._mock_download(
            spy_vs_200=1.0, qqq_slope_positive=True, vix_value=35.0
        )
        call_map = {'SPY': spy_df, 'QQQ': qqq_df, '^VIX': vix_df}

        def fake_download(ticker, **kwargs):
            return call_map.get(ticker, _make_price_df(10))

        with patch('yfinance.download', side_effect=fake_download):
            result = rpt._detect_market_regime()

        assert result['regime'] == 'RISK_OFF'

    def test_risk_off_spy_below_200ma(self):
        """SPY 200MA -3% → RISK_OFF"""
        import run_paper_trading as rpt
        spy_df, qqq_df, vix_df = self._mock_download(
            spy_vs_200=-3.0, qqq_slope_positive=True, vix_value=18.0
        )
        call_map = {'SPY': spy_df, 'QQQ': qqq_df, '^VIX': vix_df}

        def fake_download(ticker, **kwargs):
            return call_map.get(ticker, _make_price_df(10))

        with patch('yfinance.download', side_effect=fake_download):
            result = rpt._detect_market_regime()

        assert result['regime'] == 'RISK_OFF'

    def test_sideways_regime(self):
        """SPY 200MA +1%(±2% 범위), VIX=22 → SIDEWAYS"""
        import run_paper_trading as rpt
        spy_df, qqq_df, vix_df = self._mock_download(
            spy_vs_200=1.0, qqq_slope_positive=True, vix_value=22.0
        )
        call_map = {'SPY': spy_df, 'QQQ': qqq_df, '^VIX': vix_df}

        def fake_download(ticker, **kwargs):
            return call_map.get(ticker, _make_price_df(10))

        with patch('yfinance.download', side_effect=fake_download):
            result = rpt._detect_market_regime()

        assert result['regime'] == 'SIDEWAYS'

    def test_unknown_on_error(self):
        """yfinance 오류 → UNKNOWN"""
        import run_paper_trading as rpt
        with patch('yfinance.download', side_effect=Exception('network error')):
            result = rpt._detect_market_regime()
        assert result['regime'] == 'UNKNOWN'
        assert 'error' in result


# ═══════════════════════════════════════════════════════════════════
# TestGenerateRotationProposal — 제안 생성 검증
# ═══════════════════════════════════════════════════════════════════

class TestGenerateRotationProposal:

    def _regime_data(self, regime: str) -> dict:
        return {
            'regime':       regime,
            'spy_vs_200ma': 3.0,
            'qqq_slope_5d': 0.5,
            'vix_level':    16.0,
            'detected_at':  '2026-05-01 09:00:00',
        }

    def test_returns_none_on_unknown(self):
        """UNKNOWN 레짐 → None"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal({'regime': 'UNKNOWN'})
        assert result is None

    def test_proposal_is_pending(self):
        """생성된 제안은 항상 PENDING"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('TRENDING'))
        assert result is not None
        assert result['status'] == 'PENDING'

    def test_proposal_has_required_keys(self):
        """제안 dict 필수 키 존재"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('SIDEWAYS'))
        assert result is not None
        for key in ['proposed_at', 'status', 'type', 'regime', 'proposal', 'note']:
            assert key in result, f"missing key: {key}"

    def test_proposal_type_is_rotation(self):
        """type = STRATEGY_ROTATION"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('RISK_OFF'))
        assert result['type'] == 'STRATEGY_ROTATION'

    def test_risk_off_crypto_empty_in_proposal(self):
        """RISK_OFF 제안 시 CRYPTO_priority = []"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('RISK_OFF'))
        assert result['proposal']['CRYPTO_priority'] == []

    def test_trending_proposal_us_first_is_macd(self):
        """TRENDING 제안 US 첫 전략 = MACD"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('TRENDING'))
        assert result['proposal']['US_priority'][0] == 'MACD'

    def test_note_contains_no_auto_apply(self):
        """note 필드에 '자동 적용 금지' 명시"""
        from run_paper_trading import _generate_rotation_proposal
        result = _generate_rotation_proposal(self._regime_data('SIDEWAYS'))
        assert '자동 적용 금지' in result['note']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
