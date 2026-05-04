# -*- coding: utf-8 -*-
"""
Step 1 — v5.1 리스크 엔진 단위 테스트

테스트 대상:
  _check_circuit_breaker() — Daily(실현+미실현) / Weekly / Peak-Equity MDD
  calc_risk_based_position_size() — SL 기반 포지션 사이징
  settings.py 리스크 상수 존재 확인
"""
import sys
import csv
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest

# ── 임시 CSV 헬퍼 ──────────────────────────────────────────────────────
HEADER = ['open_time', 'close_time', 'ticker', 'market', 'pnl_krw', 'result']

def _make_csv(rows: list, tmp_dir: str) -> Path:
    """테스트용 임시 paper_trades.csv 생성"""
    p = Path(tmp_dir) / 'paper_trades.csv'
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def _today() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _this_monday() -> str:
    now = datetime.now()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')


INITIAL_CAP = 200_000_000  # 2억


def _base_portfolio(peak: float = None) -> dict:
    """테스트용 포트폴리오 기본값"""
    return {
        'capital':      {'KR': 50_000_000, 'US': 100_000_000, 'CRYPTO': 50_000_000},
        'peak_equity':  peak or float(INITIAL_CAP),
        'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0},
    }


# ════════════════════════════════════════════════════════════════════
# Settings 상수 확인
# ════════════════════════════════════════════════════════════════════

class TestSettingsConstants:
    def test_daily_loss_limit_exists(self):
        from config.settings import DAILY_LOSS_LIMIT
        assert DAILY_LOSS_LIMIT == -0.015, f"예상 -0.015, 실제 {DAILY_LOSS_LIMIT}"

    def test_weekly_loss_limit_exists(self):
        from config.settings import WEEKLY_LOSS_LIMIT
        assert WEEKLY_LOSS_LIMIT == -0.05, f"예상 -0.05, 실제 {WEEKLY_LOSS_LIMIT}"

    def test_mdd_limit_exists(self):
        from config.settings import MDD_LIMIT
        assert MDD_LIMIT == -0.10, f"예상 -0.10, 실제 {MDD_LIMIT}"

    def test_max_sector_positions_exists(self):
        from config.settings import MAX_SECTOR_POSITIONS
        assert MAX_SECTOR_POSITIONS == 2

    def test_risk_per_trade_pct_exists(self):
        from config.settings import RISK_PER_TRADE_PCT
        assert RISK_PER_TRADE_PCT == pytest.approx(0.003, rel=1e-3)


# ════════════════════════════════════════════════════════════════════
# Circuit Breaker — Daily (실현 손익 기준)
# ════════════════════════════════════════════════════════════════════

class TestCircuitBreakerDaily:
    def test_no_loss_passes(self, tmp_path):
        """손실 없으면 통과"""
        import run_paper_trading as rpt
        csv_file = _make_csv([], str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, reason = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is False
        assert reason == ''

    def test_daily_realized_below_limit_passes(self, tmp_path):
        """일일 실현 손실이 한도 미만이면 통과 (-1% < -1.5%)"""
        import run_paper_trading as rpt
        loss = -int(INITIAL_CAP * 0.01)   # -1% = -200만
        rows = [{'open_time': '2026-05-01 09:00:00',
                 'close_time': f'{_today()} 10:00:00',
                 'ticker': 'TEST', 'market': 'KR',
                 'pnl_krw': loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, _ = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is False

    def test_daily_realized_at_limit_halts(self, tmp_path):
        """일일 실현 손실이 -1.5% 이상이면 차단"""
        import run_paper_trading as rpt
        loss = -int(INITIAL_CAP * 0.016)  # -1.6% (한도 초과)
        rows = [{'open_time': '2026-05-01 09:00:00',
                 'close_time': f'{_today()} 10:00:00',
                 'ticker': 'TEST', 'market': 'KR',
                 'pnl_krw': loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, reason = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is True
        assert 'CB-Daily' in reason

    def test_daily_old_trades_not_counted(self, tmp_path):
        """어제 손실은 오늘 Daily CB에 포함되지 않음"""
        import run_paper_trading as rpt
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        loss = -int(INITIAL_CAP * 0.02)   # -2% (한도 초과 규모지만 어제 날짜)
        rows = [{'open_time': f'{yesterday} 09:00:00',
                 'close_time': f'{yesterday} 10:00:00',
                 'ticker': 'TEST', 'market': 'US',
                 'pnl_krw': loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, _ = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is False


# ════════════════════════════════════════════════════════════════════
# Circuit Breaker — Daily 미실현 손익 포함
# ════════════════════════════════════════════════════════════════════

class TestCircuitBreakerUnrealized:
    def test_unrealized_loss_triggers_daily_cb(self, tmp_path):
        """실현 0 + 미실현 -1.6% → Daily CB 발동"""
        import run_paper_trading as rpt
        csv_file = _make_csv([], str(tmp_path))

        # 오픈 포지션: 5,000만원 투자, 현재가 -6.4% → 미실현 -320만 (-1.6% of 2억)
        pos_data = {'positions': [{
            'ticker':   'NVDA',
            'market':   'US',
            'entry':    100.0,
            'size_krw': 50_000_000,
        }]}

        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, '_get_price', return_value=93.6):   # -6.4%
            halted, reason = rpt._check_circuit_breaker(_base_portfolio(), pos_data)

        assert halted is True
        assert 'CB-Daily' in reason
        assert '미실현' in reason

    def test_realized_plus_unrealized_combined(self, tmp_path):
        """실현 -0.8% + 미실현 -0.8% = -1.6% → CB 발동"""
        import run_paper_trading as rpt
        realized_loss = -int(INITIAL_CAP * 0.008)   # -0.8%
        rows = [{'open_time': '2026-05-01 09:00:00',
                 'close_time': f'{_today()} 10:00:00',
                 'ticker': 'AMD', 'market': 'US',
                 'pnl_krw': realized_loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))

        # 포지션: 2,000만원, -8% → 미실현 -160만 (-0.8%)
        pos_data = {'positions': [{
            'ticker':   'ETH',
            'market':   'CRYPTO',
            'entry':    100.0,
            'size_krw': 20_000_000,
        }]}

        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, '_get_price', return_value=92.0):   # -8%
            halted, reason = rpt._check_circuit_breaker(_base_portfolio(), pos_data)

        assert halted is True
        assert 'CB-Daily' in reason


# ════════════════════════════════════════════════════════════════════
# Circuit Breaker — Weekly Loss Limit
# ════════════════════════════════════════════════════════════════════

class TestCircuitBreakerWeekly:
    def test_weekly_loss_over_limit_halts(self, tmp_path):
        """이번 주 누적 손실 -5.1% → Weekly CB 발동"""
        import run_paper_trading as rpt
        # 월요일 이후 날짜로 손실 기록 (단, 오늘이면 Daily도 걸릴 수 있으므로 오늘 제외)
        # 월~어제 사이에 -5.1% 손실 기록
        monday_dt = datetime.now() - timedelta(days=datetime.now().weekday())
        if monday_dt.date() < datetime.now().date():
            trade_date = (monday_dt + timedelta(hours=10)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            # 오늘이 월요일이면 오늘 날짜 사용 (Daily보다 Weekly가 먼저 걸릴 만큼)
            trade_date = f'{_today()} 09:30:00'

        weekly_loss = -int(INITIAL_CAP * 0.051)  # -5.1%
        rows = [{'open_time': trade_date,
                 'close_time': trade_date,
                 'ticker': 'NVDA', 'market': 'US',
                 'pnl_krw': weekly_loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, reason = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is True
        assert 'CB-Weekly' in reason or 'CB-Daily' in reason   # 오늘 날짜면 Daily 먼저

    def test_weekly_loss_under_limit_passes(self, tmp_path):
        """이번 주 손실 -3% → 통과"""
        import run_paper_trading as rpt
        monday_dt = datetime.now() - timedelta(days=datetime.now().weekday())
        trade_date = (monday_dt + timedelta(hours=10)).strftime('%Y-%m-%d %H:%M:%S')

        loss = -int(INITIAL_CAP * 0.03)
        rows = [{'open_time': trade_date, 'close_time': trade_date,
                 'ticker': 'AMD', 'market': 'US',
                 'pnl_krw': loss, 'result': 'LOSS'}]
        csv_file = _make_csv(rows, str(tmp_path))
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, _ = rpt._check_circuit_breaker(_base_portfolio())
        assert halted is False


# ════════════════════════════════════════════════════════════════════
# Circuit Breaker — Peak Equity MDD
# ════════════════════════════════════════════════════════════════════

class TestCircuitBreakerMDD:
    def test_mdd_over_10pct_halts(self, tmp_path):
        """현재 자본이 피크 대비 -11% → MDD CB 발동"""
        import run_paper_trading as rpt
        csv_file = _make_csv([], str(tmp_path))

        peak = float(INITIAL_CAP)
        # 현재 자본 = 피크의 89% → MDD -11%
        current_capital = {
            'KR': int(INITIAL_CAP * 0.89 * 0.25),
            'US': int(INITIAL_CAP * 0.89 * 0.50),
            'CRYPTO': int(INITIAL_CAP * 0.89 * 0.25),
        }
        portfolio = {
            'capital':      current_capital,
            'peak_equity':  peak,
            'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0},
        }
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, reason = rpt._check_circuit_breaker(portfolio)
        assert halted is True
        assert 'CB-MDD' in reason

    def test_peak_equity_updates_on_new_high(self, tmp_path):
        """현재 자산이 피크를 넘으면 peak_equity 갱신"""
        import run_paper_trading as rpt
        csv_file = _make_csv([], str(tmp_path))

        portfolio = {
            'capital': {'KR': 60_000_000, 'US': 110_000_000, 'CRYPTO': 55_000_000},
            'peak_equity': float(INITIAL_CAP),  # 기존 피크 = 2억
            'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0},
        }
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            rpt._check_circuit_breaker(portfolio)  # 현재 2.25억 > 피크 2억

        assert portfolio['peak_equity'] > INITIAL_CAP   # 피크 갱신됨

    def test_mdd_within_limit_passes(self, tmp_path):
        """MDD -5% → 통과"""
        import run_paper_trading as rpt
        csv_file = _make_csv([], str(tmp_path))

        peak = float(INITIAL_CAP)
        # 현재 = 피크의 95% → MDD -5%
        current_capital = {
            'KR': int(INITIAL_CAP * 0.95 * 0.25),
            'US': int(INITIAL_CAP * 0.95 * 0.50),
            'CRYPTO': int(INITIAL_CAP * 0.95 * 0.25),
        }
        portfolio = {'capital': current_capital, 'peak_equity': peak,
                     'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0}}
        with patch.object(rpt, 'TRADES_FILE', csv_file):
            halted, _ = rpt._check_circuit_breaker(portfolio)
        assert halted is False


# ════════════════════════════════════════════════════════════════════
# calc_risk_based_position_size — SL 기반 사이징
# ════════════════════════════════════════════════════════════════════

class TestCalcRiskBasedPositionSize:
    def test_basic_sl_sizing(self):
        """기본 공식: position = risk_krw / sl_pct"""
        from run_paper_trading import calc_risk_based_position_size
        # total=2억, risk=0.3%=60만, SL=2% → 3,000만
        result = calc_risk_based_position_size(
            total_equity=200_000_000,
            entry_price=100.0,
            sl_price=98.0,        # SL = -2%
            risk_pct=0.003,
        )
        assert result == pytest.approx(30_000_000, rel=0.01)

    def test_higher_sl_means_smaller_position(self):
        """SL이 클수록 포지션 작아짐"""
        from run_paper_trading import calc_risk_based_position_size
        size_small_sl = calc_risk_based_position_size(200_000_000, 100.0, 98.0,  0.003)
        size_large_sl = calc_risk_based_position_size(200_000_000, 100.0, 94.0,  0.003)
        assert size_small_sl > size_large_sl

    def test_max_position_cap(self):
        """max_position_krw 상한 적용"""
        from run_paper_trading import calc_risk_based_position_size
        result = calc_risk_based_position_size(
            total_equity=200_000_000,
            entry_price=100.0,
            sl_price=99.9,          # SL 매우 작음 → 계산값 매우 큼
            risk_pct=0.003,
            max_position_krw=10_000_000,
        )
        assert result <= 10_000_000

    def test_zero_sl_returns_zero(self):
        """SL이 0이면 0 반환 (division-by-zero 방지)"""
        from run_paper_trading import calc_risk_based_position_size
        result = calc_risk_based_position_size(200_000_000, 100.0, 100.0, 0.003)
        assert result == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
