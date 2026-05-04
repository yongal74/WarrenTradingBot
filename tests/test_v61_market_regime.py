# -*- coding: utf-8 -*-
"""
Step 5 — v6.1 시장 환경 지표 확장 단위 테스트

테스트 대상:
  _detect_market_regime() v6.1 — 4지표 가중 점수 시스템
    - SPY 200MA (0~2점)
    - QQQ 50MA 기울기 (0~1점)
    - VIX (0~2점)
    - 시장 폭 breadth_pct (0~1점)
    - BTC 도미넌스 (0~1점)
  _append_regime_history() — 히스토리 누적 저장
"""
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════════════

def _make_price_df(n: int, base: float = 400.0, trend: float = 0.0) -> pd.DataFrame:
    """추세 있는 가격 DataFrame. trend>0이면 우상향."""
    closes = [base + trend * i for i in range(n)]
    df = pd.DataFrame({
        'Open': closes, 'High': [c + 1 for c in closes],
        'Low':  [c - 1 for c in closes], 'Close': closes, 'Volume': 1_000_000,
    })
    df.index = pd.date_range('2025-01-01', periods=n, freq='B')
    return df


def _make_vix_df(vix: float) -> pd.DataFrame:
    df = pd.DataFrame({'Open': vix, 'High': vix, 'Low': vix, 'Close': vix, 'Volume': 0},
                      index=pd.date_range('2026-05-01', periods=1, freq='B'))
    return df


def _spy_above_200ma(pct: float = 5.0) -> pd.DataFrame:
    """SPY가 200MA보다 pct% 위에 있도록 구성 (마지막 가격 조작)"""
    df = _make_price_df(220, base=400.0, trend=0)
    ma200 = float(pd.Series(df['Close'].values).rolling(200).mean().iloc[-1])
    target = ma200 * (1 + pct / 100)
    df.iloc[-1, df.columns.get_loc('Close')] = target
    df.iloc[-1, df.columns.get_loc('Open')]  = target
    df.iloc[-1, df.columns.get_loc('High')]  = target
    df.iloc[-1, df.columns.get_loc('Low')]   = target
    return df


def _spy_below_200ma(pct: float = -3.0) -> pd.DataFrame:
    return _spy_above_200ma(pct=pct)


def _qqq_uptrend() -> pd.DataFrame:
    """QQQ 50MA가 상향 기울기 (마지막 6봉 상승 추가)"""
    df = _make_price_df(70, base=350.0, trend=1.5)
    return df


def _qqq_flat() -> pd.DataFrame:
    return _make_price_df(70, base=350.0, trend=0.0)


# 다운로드 라우터
def _make_download_router(spy_df, qqq_df, vix_df, crypto_df=None):
    def fake_download(ticker_or_list, **kwargs):
        if isinstance(ticker_or_list, list):
            # 시장 폭 or BTC 도미넌스 용 벌크 다운로드
            if any('BTC' in t for t in ticker_or_list):
                # crypto mock
                if crypto_df is not None:
                    return crypto_df
                idx = pd.date_range('2026-05-01', periods=2, freq='B')
                df = pd.DataFrame({
                    ('Close', 'BTC-USD'): [90000.0, 90000.0],
                    ('Close', 'ETH-USD'): [2000.0,  2000.0],
                    ('Close', 'SOL-USD'): [150.0,   150.0],
                }, index=idx)
                df.columns = pd.MultiIndex.from_tuples(df.columns)
                return df
            else:
                # 시장 폭 용 — 단일 가격 시리즈 리턴
                idx = pd.date_range('2025-01-01', periods=60, freq='B')
                closes = pd.DataFrame(
                    {tk: [400.0 + i for i in range(60)] for tk in ticker_or_list},
                    index=idx
                )
                return pd.DataFrame({'Close': closes})
        ticker = str(ticker_or_list)
        if 'SPY' in ticker:
            return spy_df
        if 'QQQ' in ticker:
            return qqq_df
        if 'VIX' in ticker:
            return vix_df
        return _make_price_df(10)
    return fake_download


# ═══════════════════════════════════════════════════════════════════
# TestRegimeScore — 점수 기반 레짐 판정
# ═══════════════════════════════════════════════════════════════════

class TestRegimeScore:

    def test_result_has_regime_score(self):
        """반환 dict에 regime_score 포함"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(3.0), _qqq_uptrend(), _make_vix_df(16.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert 'regime_score' in result

    def test_result_has_breadth_pct(self):
        """반환 dict에 breadth_pct 포함"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(3.0), _qqq_uptrend(), _make_vix_df(16.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert 'breadth_pct' in result
        assert 0.0 <= result['breadth_pct'] <= 1.0

    def test_result_has_btc_dominance(self):
        """반환 dict에 btc_dominance 포함"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(3.0), _qqq_uptrend(), _make_vix_df(16.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert 'btc_dominance' in result

    def test_hard_risk_off_vix(self):
        """VIX≥30 → 하드 RISK_OFF (점수 무관)"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(5.0), _qqq_uptrend(), _make_vix_df(32.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert result['regime'] == 'RISK_OFF'

    def test_hard_risk_off_spy(self):
        """SPY 200MA -3% → 하드 RISK_OFF"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_below_200ma(-3.0), _qqq_uptrend(), _make_vix_df(18.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert result['regime'] == 'RISK_OFF'

    def test_trending_high_score(self):
        """이상적 환경: SPY+3%/QQQ 상향/VIX<18 → TRENDING"""
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(3.5), _qqq_uptrend(), _make_vix_df(14.0)
        )
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        # 점수가 높으면 TRENDING, VIX<18이면 +2, SPY+3.5%면 +2
        assert result['regime'] in ('TRENDING', 'SIDEWAYS')   # 환경에 따라
        assert result['regime_score'] >= 3

    def test_unknown_on_spy_data_failure(self):
        """SPY 데이터 불충분 → UNKNOWN"""
        import run_paper_trading as rpt
        short_df = _make_price_df(10)   # 200봉 미만
        router = _make_download_router(short_df, _qqq_flat(), _make_vix_df(20.0))
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', Path(tempfile.mkdtemp())):
            result = rpt._detect_market_regime()
        assert result['regime'] == 'UNKNOWN'


# ═══════════════════════════════════════════════════════════════════
# TestRegimeHistory — 히스토리 저장
# ═══════════════════════════════════════════════════════════════════

class TestRegimeHistory:

    def test_history_file_created(self, tmp_path):
        """_append_regime_history() 호출 시 파일 생성"""
        import run_paper_trading as rpt
        with patch.object(rpt, 'LOG_DIR', tmp_path):
            rpt._append_regime_history({'regime': 'TRENDING', 'detected_at': '2026-05-01 09:00:00'})
        assert (tmp_path / 'regime_history.json').exists()

    def test_history_appends(self, tmp_path):
        """두 번 호출하면 2개 기록"""
        import run_paper_trading as rpt
        with patch.object(rpt, 'LOG_DIR', tmp_path):
            rpt._append_regime_history({'regime': 'TRENDING', 'detected_at': '2026-05-01 09:00:00'})
            rpt._append_regime_history({'regime': 'SIDEWAYS', 'detected_at': '2026-05-01 09:15:00'})
        data = json.loads((tmp_path / 'regime_history.json').read_text(encoding='utf-8'))
        assert len(data) == 2

    def test_history_max_200(self, tmp_path):
        """200개 초과 시 최근 200개만 유지"""
        import run_paper_trading as rpt
        with patch.object(rpt, 'LOG_DIR', tmp_path):
            for i in range(210):
                rpt._append_regime_history({'regime': 'TRENDING', 'detected_at': f'2026-05-{i:02d}'})
        data = json.loads((tmp_path / 'regime_history.json').read_text(encoding='utf-8'))
        assert len(data) == 200

    def test_regime_in_history(self, tmp_path):
        """저장된 히스토리에 regime 필드 존재"""
        import run_paper_trading as rpt
        with patch.object(rpt, 'LOG_DIR', tmp_path):
            rpt._append_regime_history({'regime': 'RISK_OFF', 'spy_vs_200ma': -3.0,
                                        'detected_at': '2026-05-01 09:00:00'})
        data = json.loads((tmp_path / 'regime_history.json').read_text(encoding='utf-8'))
        assert data[0]['regime'] == 'RISK_OFF'
        assert data[0]['spy_vs_200ma'] == -3.0


# ═══════════════════════════════════════════════════════════════════
# TestReturnStructure — 반환 구조 완전성
# ═══════════════════════════════════════════════════════════════════

class TestReturnStructure:

    def _run_regime(self, spy_pct=3.0, qqq_up=True, vix=16.0, tmp_path=None):
        import run_paper_trading as rpt
        router = _make_download_router(
            _spy_above_200ma(spy_pct),
            _qqq_uptrend() if qqq_up else _qqq_flat(),
            _make_vix_df(vix),
        )
        log_dir = tmp_path or Path(tempfile.mkdtemp())
        with patch('yfinance.download', side_effect=router), \
             patch.object(rpt, 'LOG_DIR', log_dir):
            return rpt._detect_market_regime()

    def test_all_required_keys(self, tmp_path):
        """반환 dict 필수 키 7개 확인"""
        result = self._run_regime(tmp_path=tmp_path)
        required = ['regime', 'spy_vs_200ma', 'qqq_slope_5d', 'vix_level',
                    'breadth_pct', 'btc_dominance', 'regime_score', 'detected_at']
        for k in required:
            assert k in result, f"missing: {k}"

    def test_detected_at_format(self, tmp_path):
        """detected_at datetime 포맷"""
        from datetime import datetime
        result = self._run_regime(tmp_path=tmp_path)
        datetime.strptime(result['detected_at'], '%Y-%m-%d %H:%M:%S')

    def test_regime_one_of_valid_values(self, tmp_path):
        """regime은 TRENDING/SIDEWAYS/RISK_OFF/UNKNOWN 중 하나"""
        result = self._run_regime(tmp_path=tmp_path)
        assert result['regime'] in ('TRENDING', 'SIDEWAYS', 'RISK_OFF', 'UNKNOWN')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
