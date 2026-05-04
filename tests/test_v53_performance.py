# -*- coding: utf-8 -*-
"""
Step 3 — v5.3 성과 분석 엔진 단위 테스트

테스트 대상:
  _compute_performance_report() — 30일/90일/전체 윈도우 × ticker/전략별
  _save_perf_report()           — JSON 저장 확인
  윈도우 필터링                  — close_time 기준 날짜 필터
  엣지 케이스                    — 데이터 없음 / 전부 WIN / 전부 LOSS
"""
import sys
import csv
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 헬퍼: CSV 임시 생성
# ═══════════════════════════════════════════════════════════════════

TRADES_HEADER = [
    'open_time', 'close_time', 'ticker', 'name', 'market', 'timeframe',
    'signal_type', 'entry', 'exit', 'sl', 'tp',
    'size_krw', 'pnl_pct', 'pnl_krw', 'result', 'close_reason',
    'tp_stage', 'quality_score', 'quality_tags', 'hold_minutes',
    'entry_hour_kst', 'vol_ratio',
    'has_vol_spike', 'has_liq_sweep',
    'has_choch', 'has_body_in_zone',
    'has_pinbar', 'has_ema_align', 'has_fresh_zone',
]


def _make_csv(rows: list[dict], path: Path) -> None:
    """rows 리스트를 CSV로 저장. 빠진 컬럼은 '' 채움."""
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=TRADES_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in TRADES_HEADER})


def _row(ticker='NVDA', market='US', signal_type='MACD',
         pnl_krw=100_000, days_ago=5) -> dict:
    """단일 거래 행 생성. days_ago=0이면 오늘 close."""
    close_dt = datetime.now() - timedelta(days=days_ago)
    open_dt  = close_dt - timedelta(hours=2)
    return {
        'open_time':   open_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'close_time':  close_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'ticker':      ticker,
        'market':      market,
        'signal_type': signal_type,
        'pnl_krw':     str(pnl_krw),
        'result':      'WIN' if pnl_krw > 0 else 'LOSS',
        'size_krw':    '10000000',
    }


# ═══════════════════════════════════════════════════════════════════
# TestWindowFiltering — 날짜 필터 검증
# ═══════════════════════════════════════════════════════════════════

class TestWindowFiltering:

    def test_30d_excludes_old_trades(self, tmp_path):
        """60일 전 거래는 30d 윈도우에서 제외됨"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(pnl_krw=200_000, days_ago=60),   # 제외
            _row(pnl_krw=100_000, days_ago=10),   # 포함
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['all']['trades'] == 2
        assert report['windows']['30d']['trades'] == 1

    def test_90d_excludes_120d_old_trades(self, tmp_path):
        """120일 전 거래는 90d 윈도우에서 제외됨"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(pnl_krw=100_000, days_ago=120),  # 제외
            _row(pnl_krw=100_000, days_ago=30),   # 포함
            _row(pnl_krw=100_000, days_ago=5),    # 포함
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['90d']['trades'] == 2
        assert report['windows']['all']['trades'] == 3

    def test_all_window_includes_everything(self, tmp_path):
        """all 윈도우는 전체 기간 포함"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(days_ago=200),
            _row(days_ago=100),
            _row(days_ago=10),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['all']['trades'] == 3


# ═══════════════════════════════════════════════════════════════════
# TestMetricsFormula — PF/Expectancy/Sharpe/MDD 공식 검증
# ═══════════════════════════════════════════════════════════════════

class TestMetricsFormula:

    def test_profit_factor(self, tmp_path):
        """PF = 총이익 / 총손실 = 3:1"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(pnl_krw=300_000),   # WIN
            _row(pnl_krw=-100_000),  # LOSS
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['all']['profit_factor'] == pytest.approx(3.0, rel=0.01)

    def test_win_rate(self, tmp_path):
        """승률 = 2/3 = 66.7%"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(pnl_krw=100_000),
            _row(pnl_krw=100_000),
            _row(pnl_krw=-100_000),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['all']['win_rate'] == pytest.approx(66.7, abs=0.2)

    def test_expectancy(self, tmp_path):
        """Expectancy = WR*avgW - LR*avgL = 0.5*100K - 0.5*50K = 25K"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(pnl_krw=100_000),
            _row(pnl_krw=-50_000),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        exp = report['windows']['all']['expectancy_krw']
        assert exp == pytest.approx(25_000, abs=500)

    def test_mdd_calculation(self, tmp_path):
        """MDD: +10만, -30만, +10만 → peak=10만, trough=-20만 → MDD=-300%"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        # 누적: 100K → -200K → -100K → peak=100K, MDD=(−200K−100K)/100K = −3.0
        _make_csv([
            _row(pnl_krw=100_000,  days_ago=30),
            _row(pnl_krw=-300_000, days_ago=20),
            _row(pnl_krw=100_000,  days_ago=10),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        mdd = report['windows']['all']['max_drawdown_pct']
        assert mdd < 0   # 음수여야 함
        assert mdd == pytest.approx(-300.0, abs=1.0)

    def test_all_win_pf_is_inf(self, tmp_path):
        """전부 WIN → PF = inf"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([_row(pnl_krw=100_000), _row(pnl_krw=200_000)], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['all']['profit_factor'] == float('inf')


# ═══════════════════════════════════════════════════════════════════
# TestBreakdown — ticker별/전략별 분류
# ═══════════════════════════════════════════════════════════════════

class TestBreakdown:

    def test_by_ticker_keys(self, tmp_path):
        """ticker별 분류 키 존재 확인"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(ticker='NVDA', pnl_krw=100_000),
            _row(ticker='AMD',  pnl_krw=-50_000),
            _row(ticker='NVDA', pnl_krw=200_000),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert 'NVDA' in report['by_ticker']
        assert 'AMD'  in report['by_ticker']
        assert report['by_ticker']['NVDA']['trades'] == 2

    def test_by_strategy_keys(self, tmp_path):
        """전략별 분류 키 존재 확인"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(signal_type='MACD',        pnl_krw=100_000),
            _row(signal_type='BB_REVERSAL', pnl_krw=-50_000),
            _row(signal_type='MACD',        pnl_krw=150_000),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert 'MACD'        in report['by_strategy']
        assert 'BB_REVERSAL' in report['by_strategy']
        assert report['by_strategy']['MACD']['trades'] == 2

    def test_ticker_win_rate(self, tmp_path):
        """NVDA 3WIN 1LOSS → WR 75%"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([
            _row(ticker='NVDA', pnl_krw=100_000),
            _row(ticker='NVDA', pnl_krw=100_000),
            _row(ticker='NVDA', pnl_krw=100_000),
            _row(ticker='NVDA', pnl_krw=-100_000),
        ], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['by_ticker']['NVDA']['win_rate'] == pytest.approx(75.0, abs=0.2)


# ═══════════════════════════════════════════════════════════════════
# TestEdgeCases — 엣지 케이스
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_no_trades_file_returns_empty(self, tmp_path):
        """CSV 없으면 빈 report 반환"""
        import run_paper_trading as rpt
        missing = tmp_path / 'nonexistent.csv'
        perf_file = tmp_path / 'performance_report.json'
        with patch.object(rpt, 'TRADES_FILE', missing), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows'] == {}
        assert report['by_ticker'] == {}
        assert report['by_strategy'] == {}

    def test_empty_window_returns_zero_trades(self, tmp_path):
        """30d 윈도우에 해당 거래 없으면 trades=0"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([_row(days_ago=60)], csv_file)   # 30d 범위 밖
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        assert report['windows']['30d']['trades'] == 0

    def test_report_saved_to_json(self, tmp_path):
        """performance_report.json 파일이 올바르게 저장됨"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([_row(pnl_krw=100_000)], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            rpt._compute_performance_report()

        assert perf_file.exists()
        data = json.loads(perf_file.read_text(encoding='utf-8'))
        assert 'generated_at' in data
        assert 'windows' in data
        assert 'by_ticker' in data

    def test_generated_at_format(self, tmp_path):
        """generated_at 필드가 datetime 포맷 준수"""
        import run_paper_trading as rpt
        csv_file = tmp_path / 'paper_trades.csv'
        perf_file = tmp_path / 'performance_report.json'
        _make_csv([], csv_file)
        with patch.object(rpt, 'TRADES_FILE', csv_file), \
             patch.object(rpt, 'PERF_REPORT_FILE', perf_file):
            report = rpt._compute_performance_report()

        datetime.strptime(report['generated_at'], '%Y-%m-%d %H:%M:%S')   # 파싱 성공해야 함


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
