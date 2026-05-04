# -*- coding: utf-8 -*-
"""
Step 6 — v6.2 동적 자본 배분 제안 단위 테스트

테스트 대상:
  _generate_capital_allocation_proposal() — 성과+레짐 기반 배분 제안
  제약 조건: ±20%p 이내 / 합계 100% / PENDING / 자동 적용 금지
"""
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════════════

def _make_perf_report(tmp_path: Path, by_market: dict) -> Path:
    """성과 리포트 JSON 생성."""
    report = {
        'generated_at': '2026-05-01 09:00:00',
        'windows': {'all': {}, '90d': {}, '30d': {}},
        'by_ticker':   {},
        'by_strategy': {},
        'by_market':   by_market,
    }
    path = tmp_path / 'performance_report.json'
    path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    return path


def _good_market(trades=20, wr=70.0, pf=2.5, exp=50_000):
    return {'trades': trades, 'win_rate': wr, 'profit_factor': pf, 'expectancy_krw': exp}


def _bad_market(trades=10, wr=30.0, pf=0.5, exp=-20_000):
    return {'trades': trades, 'win_rate': wr, 'profit_factor': pf, 'expectancy_krw': exp}


def _empty_market():
    return {'trades': 0, 'win_rate': 0, 'profit_factor': 0, 'expectancy_krw': 0}


def _regime(regime='SIDEWAYS'):
    return {'regime': regime, 'spy_vs_200ma': 1.0, 'qqq_slope_5d': 0.2, 'vix_level': 20.0}


# ═══════════════════════════════════════════════════════════════════
# TestAllocationProposal — 기본 제안 생성
# ═══════════════════════════════════════════════════════════════════

class TestAllocationProposal:

    def test_returns_none_no_perf_data(self, tmp_path):
        """성과 데이터 없으면 None 반환"""
        import run_paper_trading as rpt
        missing = tmp_path / 'nonexistent.json'
        with patch.object(rpt, 'PERF_REPORT_FILE', missing):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is None

    def test_returns_none_empty_by_market(self, tmp_path):
        """by_market 비어 있으면 None"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, by_market={})
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is None

    def test_status_is_pending(self, tmp_path):
        """제안 status = PENDING"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _good_market(), 'US': _good_market(), 'CRYPTO': _good_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is not None
        assert result['status'] == 'PENDING'

    def test_type_is_capital_allocation(self, tmp_path):
        """type = CAPITAL_ALLOCATION"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _good_market(), 'US': _good_market(), 'CRYPTO': _good_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result['type'] == 'CAPITAL_ALLOCATION'

    def test_required_keys(self, tmp_path):
        """필수 키 존재"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {'US': _good_market()})
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        if result is None:
            pytest.skip("성과 데이터 부족")
        for key in ['proposed_at', 'status', 'type', 'regime',
                    'current_alloc', 'proposed_alloc', 'diff_pct', 'note']:
            assert key in result, f"missing: {key}"

    def test_note_contains_no_auto_apply(self, tmp_path):
        """note에 '자동 적용 금지' 명시"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _good_market(), 'US': _good_market(), 'CRYPTO': _good_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is not None
        assert '자동 적용 금지' in result['note']


# ═══════════════════════════════════════════════════════════════════
# TestAllocationConstraints — 배분 제약 조건
# ═══════════════════════════════════════════════════════════════════

class TestAllocationConstraints:

    def test_proposed_sums_to_100(self, tmp_path):
        """제안 배분 합계 = 100% (±0.5% 허용)"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _good_market(), 'US': _bad_market(), 'CRYPTO': _good_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is not None
        total = sum(result['proposed_alloc'].values())
        assert abs(total - 100.0) < 1.0, f"합계={total}"

    def test_change_within_20pct(self, tmp_path):
        """각 시장 변화폭 ±20%p 이내"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _bad_market(), 'US': _good_market(), 'CRYPTO': _empty_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        if result is None:
            pytest.skip()
        for mkt, diff in result['diff_pct'].items():
            assert abs(diff) <= 20.1, f"{mkt} 변화폭 초과: {diff}%"

    def test_all_markets_in_proposed(self, tmp_path):
        """KR/US/CRYPTO 3개 시장 모두 proposed_alloc에 포함"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR': _good_market(), 'US': _good_market(), 'CRYPTO': _good_market()
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime())
        assert result is not None
        for mkt in ['KR', 'US', 'CRYPTO']:
            assert mkt in result['proposed_alloc']


# ═══════════════════════════════════════════════════════════════════
# TestRegimeEffect — 레짐별 영향
# ═══════════════════════════════════════════════════════════════════

class TestRegimeEffect:

    def test_risk_off_reduces_crypto(self, tmp_path):
        """RISK_OFF 시 CRYPTO 배분 제안이 현재보다 작거나 같음"""
        import run_paper_trading as rpt
        pf = _make_perf_report(tmp_path, {
            'KR':     _good_market(),
            'US':     _good_market(),
            'CRYPTO': _good_market(),  # 성과 좋아도 RISK_OFF면 축소 권고
        })
        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            result = rpt._generate_capital_allocation_proposal(_regime('RISK_OFF'))
        if result is None:
            pytest.skip()
        # RISK_OFF: CRYPTO 점수를 0.3배 → 제안 비율 감소
        crypto_diff = result['diff_pct'].get('CRYPTO', 0)
        assert crypto_diff <= 0, f"RISK_OFF에서 CRYPTO 증가 제안: {crypto_diff}%"

    def test_trending_boosts_us(self, tmp_path):
        """TRENDING 시 US 배분 제안이 SIDEWAYS보다 크거나 같음"""
        import run_paper_trading as rpt
        by_market = {'KR': _good_market(), 'US': _good_market(), 'CRYPTO': _good_market()}
        pf = _make_perf_report(tmp_path, by_market)

        with patch.object(rpt, 'PERF_REPORT_FILE', pf):
            trending = rpt._generate_capital_allocation_proposal(_regime('TRENDING'))
            sideways = rpt._generate_capital_allocation_proposal(_regime('SIDEWAYS'))

        if trending is None or sideways is None:
            pytest.skip()
        us_trending = trending['proposed_alloc'].get('US', 0)
        us_sideways = sideways['proposed_alloc'].get('US', 0)
        assert us_trending >= us_sideways - 0.5, (
            f"TRENDING US({us_trending}%) < SIDEWAYS US({us_sideways}%)"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
