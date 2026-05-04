# -*- coding: utf-8 -*-
"""
Step 7 — v7.0 AI 운영 에이전트 단위 테스트

테스트 대상:
  _detect_anomalies()     — 이상 감지 (연속손실/섹터집중/장기보유/대형손실)
  _generate_daily_report() — 일일 리포트 생성 + JSON 저장
  거래 실행 없음 확인       — 리포트만 생성, 주문 함수 미호출
"""
import sys
import csv
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 헬퍼
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


def _write_trades(rows: list[dict], path: Path):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=TRADES_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in TRADES_HEADER})


def _trade_row(result='WIN', days_ago=1):
    close_dt = datetime.now() - timedelta(days=days_ago)
    return {
        'open_time':  (close_dt - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
        'close_time': close_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'ticker':     'NVDA', 'market': 'US', 'result': result,
        'pnl_krw':   '100000' if result == 'WIN' else '-50000',
    }


def _open_position(ticker='NVDA', market='US', entry=200.0, days_ago=1):
    open_dt = datetime.now() - timedelta(days=days_ago)
    return {
        'ticker':     ticker,
        'name':       ticker,
        'market':     market,
        'timeframe':  'daily',
        'entry':      entry,
        'sl':         entry * 0.97,
        'tp':         entry * 1.06,
        'size_krw':   10_000_000,
        'open_time':  open_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'signal_type': 'MACD',
    }


def _portfolio():
    return {
        'capital':       {'KR': 50_000_000, 'US': 100_000_000, 'CRYPTO': 50_000_000},
        'realized_pnl':  {'KR': 0, 'US': 100_000, 'CRYPTO': -50_000},
        'total_trades':  10,
        'wins':          6,
        'start_date':    '2026-04-01',
        'peak_equity':   200_050_000,
    }


# ═══════════════════════════════════════════════════════════════════
# TestDetectAnomalies — 이상 감지
# ═══════════════════════════════════════════════════════════════════

class TestDetectAnomalies:

    def test_no_anomaly_on_clean_state(self, tmp_path):
        """정상 상태 → 이상 없음"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([_trade_row('WIN') for _ in range(5)], csv_path)
        pos_data = {'positions': [_open_position(days_ago=1)]}
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies(pos_data, _portfolio())
        assert isinstance(result, list)
        # 연속 손실 없음, 장기 보유 없음
        types = [a['type'] for a in result]
        assert 'CONSECUTIVE_LOSS' not in types

    def test_consecutive_loss_detected(self, tmp_path):
        """최근 3연속 LOSS → CONSECUTIVE_LOSS 이상 감지"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        rows = (
            [_trade_row('WIN')] * 5 +
            [_trade_row('LOSS')] * 3
        )
        _write_trades(rows, csv_path)
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies({'positions': []}, _portfolio())
        types = [a['type'] for a in result]
        assert 'CONSECUTIVE_LOSS' in types

    def test_long_hold_detected(self, tmp_path):
        """5일 이상 보유 포지션 → LONG_HOLD 이상 감지"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([], csv_path)
        pos_data = {'positions': [_open_position(days_ago=6)]}  # 6일 전 진입
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies(pos_data, _portfolio())
        types = [a['type'] for a in result]
        assert 'LONG_HOLD' in types

    def test_no_long_hold_for_fresh_position(self, tmp_path):
        """1일 보유 → LONG_HOLD 없음"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([], csv_path)
        pos_data = {'positions': [_open_position(days_ago=1)]}
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies(pos_data, _portfolio())
        types = [a['type'] for a in result]
        assert 'LONG_HOLD' not in types

    def test_anomaly_has_required_keys(self, tmp_path):
        """이상 항목 dict에 type/severity/message/detail 존재"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([_trade_row('LOSS')] * 5, csv_path)
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies({'positions': []}, _portfolio())
        if result:
            for a in result:
                assert 'type'     in a
                assert 'severity' in a
                assert 'message'  in a
                assert 'detail'   in a

    def test_severity_values(self, tmp_path):
        """severity는 HIGH/MEDIUM/LOW 중 하나"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([_trade_row('LOSS')] * 5, csv_path)
        pos_data = {'positions': [_open_position(days_ago=6)]}
        with patch.object(rpt, 'TRADES_FILE', csv_path):
            result = rpt._detect_anomalies(pos_data, _portfolio())
        for a in result:
            assert a['severity'] in ('HIGH', 'MEDIUM', 'LOW')


# ═══════════════════════════════════════════════════════════════════
# TestDailyReport — 일일 리포트 생성
# ═══════════════════════════════════════════════════════════════════

class TestDailyReport:

    def _run_report(self, tmp_path):
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([_trade_row('WIN'), _trade_row('LOSS')], csv_path)
        pos_data  = {'positions': [_open_position()]}
        portfolio = _portfolio()
        with patch.object(rpt, 'TRADES_FILE', csv_path), \
             patch.object(rpt, 'LOG_DIR', tmp_path), \
             patch.object(rpt, 'PERF_REPORT_FILE', tmp_path / 'performance_report.json'):
            (tmp_path / 'journal').mkdir(exist_ok=True)
            return rpt._generate_daily_report(pos_data, portfolio)

    def test_report_has_required_keys(self, tmp_path):
        """리포트 dict 필수 키 확인"""
        report = self._run_report(tmp_path)
        for k in ['generated_at', 'date', 'summary', 'performance',
                  'regime', 'anomalies', 'open_positions', 'recommendations']:
            assert k in report, f"missing: {k}"

    def test_report_saved_to_journal(self, tmp_path):
        """journal 디렉토리에 JSON 파일 저장"""
        self._run_report(tmp_path)
        today = datetime.now().strftime('%Y-%m-%d')
        assert (tmp_path / 'journal' / f'{today}-ai_report.json').exists()

    def test_summary_fields(self, tmp_path):
        """summary에 기본 필드 존재"""
        report = self._run_report(tmp_path)
        s = report['summary']
        for k in ['total_initial_krw', 'total_current_krw', 'total_realized_pnl',
                  'return_pct', 'total_trades', 'win_rate', 'open_positions']:
            assert k in s, f"summary missing: {k}"

    def test_open_positions_list(self, tmp_path):
        """오픈 포지션이 있으면 open_positions 리스트에 포함"""
        report = self._run_report(tmp_path)
        assert isinstance(report['open_positions'], list)
        assert len(report['open_positions']) == 1

    def test_recommendations_is_list(self, tmp_path):
        """recommendations는 리스트"""
        report = self._run_report(tmp_path)
        assert isinstance(report['recommendations'], list)

    def test_no_trade_execution(self, tmp_path):
        """리포트 생성 시 주문 함수(open_positions) 미호출"""
        import run_paper_trading as rpt
        csv_path = tmp_path / 'paper_trades.csv'
        _write_trades([], csv_path)
        pos_data  = {'positions': []}
        portfolio = _portfolio()
        with patch.object(rpt, 'TRADES_FILE', csv_path), \
             patch.object(rpt, 'LOG_DIR', tmp_path), \
             patch.object(rpt, 'PERF_REPORT_FILE', tmp_path / 'perf.json'), \
             patch.object(rpt, 'open_positions', MagicMock()) as mock_op:
            (tmp_path / 'journal').mkdir(exist_ok=True)
            rpt._generate_daily_report(pos_data, portfolio)
        # 주문 함수가 절대 호출되지 않아야 함
        mock_op.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
