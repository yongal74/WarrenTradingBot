# -*- coding: utf-8 -*-
"""
Warren Paper Trading v5.1 — 30종목 전체 (KR16 + US10 + CRYPTO4)
가상 자금으로 FVG+OB★ + 종목별 확정전략 실거래 시뮬레이션

실행:
  python run_paper_trading.py          # 즉시 1회 스캔
  python run_paper_trading.py --loop   # 15분마다 자동 반복
  python run_paper_trading.py --status # 현재 포지션/성과 출력

포트폴리오:
  KR  (16종목): 50,000,000원  포지션당 5,000,000원 최대5개
  US  (10종목): 100,000,000원 포지션당 10,000,000원 최대5개
  CRYPTO(4종목): 50,000,000원 포지션당 5,000,000원 최대5개
  합계:         200,000,000원

리스크:
  일일 손실 한도: -1.5%  (실현+미실현)
  주간 손실 한도: -5.0%
  MDD 한도:      -10.0% (Peak Equity 기준)
  섹터 집중도:   동일 섹터 최대 2포지션

로그:
  logs/paper_positions.json  — 오픈 포지션
  logs/paper_trades.csv      — 완료된 거래
  logs/paper_portfolio.json  — 포트폴리오 현황 (메트릭 포함)
"""
import sys
import json
import csv
import time
import argparse
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass

import yfinance as yf
from core.fvg_ob_tester import (
    scan_all,
    KR_SWING_TICKERS, US_SWING_TICKERS,
    CRYPTO_TICKERS, CRYPTO_4H_TICKERS,
)

# ── 하드 화이트리스트 (모듈 레벨 — 1회만 생성) ──────────────────
# open_positions() 매 호출마다 import하던 것을 여기로 이동
_HARD_WL: dict[str, set] = {
    'KR':     set(KR_SWING_TICKERS.keys()),
    'US':     set(US_SWING_TICKERS.keys()),
    'CRYPTO': set(CRYPTO_TICKERS.keys()) | set(CRYPTO_4H_TICKERS.keys()),
}

# ── 경로 ────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
LOG_DIR     = BASE_DIR / 'logs'
POS_FILE    = LOG_DIR / 'paper_positions.json'
TRADES_FILE = LOG_DIR / 'paper_trades.csv'
PORT_FILE   = LOG_DIR / 'paper_portfolio.json'
LOCK_FILE   = LOG_DIR / 'paper_trading.lock'
PERF_REPORT_FILE = LOG_DIR / 'performance_report.json'   # V5.3
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 프로세스 락 — 동시 실행 방지 ────────────────────────────────
import os, atexit

def _acquire_lock() -> bool:
    """원자적 파일 생성으로 중복 실행 방지 (TOCTOU 레이스 컨디션 제거)."""
    # 오래된 락 파일 정리 (10분 초과)
    if LOCK_FILE.exists():
        try:
            age = datetime.now().timestamp() - LOCK_FILE.stat().st_mtime
            if age < 600:
                print(f"[LOCK] 다른 프로세스 실행 중 (락 {age:.0f}초 전) — 종료")
                return False
        except Exception:
            pass
        LOCK_FILE.unlink(missing_ok=True)
    # 원자적 배타적 생성 (open 'x' — 이미 있으면 FileExistsError)
    try:
        with open(LOCK_FILE, 'x') as f:
            f.write(str(os.getpid()))
        atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))
        return True
    except FileExistsError:
        print(f"[LOCK] 다른 프로세스가 락 선점 — 종료")
        return False

# ── 가상 자금 설정 (v4.5) ────────────────────────────────────────
INITIAL_CAPITAL = {
    'KR':     50_000_000,   # 5,000만
    'US':    100_000_000,   # 1억
    'CRYPTO': 50_000_000,   # 5,000만
}
# 시장별 고정 포지션 크기 (v4.6 확정)
# KR: 5,000만 ÷ 10포지션 = 500만 (포지션당 리스크 1% → 안전)
# US: 1억 ÷ 10포지션 = 1,000만 (달러환산 약 $7,000)
# CRYPTO: 5,000만 ÷ 10포지션 = 500만 (변동성 고려 축소)
POSITION_SIZE = {
    'KR':     5_000_000,    # 500만원/건
    'US':    10_000_000,    # 1,000만원/건
    'CRYPTO': 5_000_000,    # 500만원/건
}
MAX_POS_PER_MARKET = {
    'KR':     5,    # 500만 × 5 = 2,500만
    'US':     5,    # 1,000만 × 5 = 5,000만
    'CRYPTO': 5,    # 2,000만 × 5 = 1억 (초과방지)
}

# 현재가 조회용 티커 매핑
YF_TICKER = {
    # KR V4.0 (16종목)
    '017670': '017670.KS', '035720': '035720.KS',
    '021240': '021240.KS', '005380': '005380.KS',
    '010140': '010140.KS', '086790': '086790.KS',
    '034020': '034020.KS', '272210': '272210.KS',
    '000660': '000660.KS', '058470': '058470.KS',
    '064350': '064350.KS', '128940': '128940.KS',
    '012450': '012450.KS',
    '008060': '008060.KS', '005930': '005930.KS', '009150': '009150.KS',
    # US V4.0 (10종목)
    'AMD': 'AMD', 'MU': 'MU', 'NVDA': 'NVDA', 'AVGO': 'AVGO', 'MSTR': 'MSTR',
    'LRCX': 'LRCX', 'AMZN': 'AMZN', 'SHOP': 'SHOP', 'GOOGL': 'GOOGL', 'TSLA': 'TSLA',
    # CRYPTO V4.0 (4종목)
    'SOL': 'SOL-USD', 'ETH': 'ETH-USD', 'BTC': 'BTC-USD', 'XRP': 'XRP-USD',
}

# ── V5.0: 섹터 매핑 (동일 섹터 최대 2포지션) ───────────────────────
SECTOR_MAP: dict = {
    # KR
    '005930': '반도체', '000660': '반도체', '009150': '반도체',
    '008060': '반도체', '058470': '반도체',
    '064350': '방산',   '012450': '방산',   '272210': '방산',
    '128940': '바이오', '017670': '통신',   '035720': 'IT',
    '021240': '생활',   '005380': '자동차', '010140': '조선',
    '086790': '금융',   '034020': '에너지',
    # US
    'AMD': '반도체US', 'MU': '반도체US', 'NVDA': '반도체US',
    'AVGO': '반도체US', 'LRCX': '반도체US',
    'MSTR': '크립토자산', 'AMZN': '빅테크', 'SHOP': '이커머스',
    'GOOGL': '빅테크', 'TSLA': '전기차',
    # CRYPTO — 각자 별도 섹터 (집중도 제한 불필요)
    'BTC': 'BTC', 'ETH': 'ETH', 'SOL': 'SOL', 'XRP': 'XRP',
}
try:
    from config.settings import MAX_SECTOR_POSITIONS, RISK_PER_TRADE_PCT
except ImportError:
    MAX_SECTOR_POSITIONS = 2
    RISK_PER_TRADE_PCT   = 0.003

TRADES_HEADER = [
    'open_time', 'close_time', 'ticker', 'name', 'market', 'timeframe',
    'signal_type', 'entry', 'exit', 'sl', 'tp',
    'size_krw', 'pnl_pct', 'pnl_krw', 'result', 'close_reason',
    'tp_stage', 'quality_score', 'quality_tags', 'hold_minutes',
    'entry_hour_kst', 'vol_ratio',
    'has_vol_spike', 'has_liq_sweep',
    'has_choch', 'has_body_in_zone',
    'has_pinbar', 'has_ema_align',
    'has_fresh_zone',
]


# ── 포지션 파일 I/O ──────────────────────────────────────────────
def _load_positions() -> dict:
    if POS_FILE.exists():
        try:
            return json.loads(POS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'positions': [], 'daily_counts': {}}


def _save_positions(data: dict):
    save_data = {k: v for k, v in data.items() if k != '_closed_today_runtime'}
    POS_FILE.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding='utf-8')


def _load_portfolio() -> dict:
    if PORT_FILE.exists():
        try:
            return json.loads(PORT_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        'start_date': datetime.now().strftime('%Y-%m-%d'),
        'capital':    dict(INITIAL_CAPITAL),
        'realized_pnl': {'KR': 0, 'US': 0, 'CRYPTO': 0},
        'total_trades': 0,
        'wins': 0,
        'losses': 0,
        'history': [],
    }


def _save_portfolio(port: dict):
    # 저장 전 win_rate_pct 자동 갱신
    total = port.get('total_trades', 0)
    wins  = port.get('wins', 0)
    port['win_rate_pct'] = round(wins / total * 100, 1) if total > 0 else 0
    port['total_realized_krw'] = int(sum(port.get('realized_pnl', {}).values()))
    # Peak Equity 초기화 (없으면 initial_capital 합계로 설정)
    if 'peak_equity' not in port:
        port['peak_equity'] = float(sum(INITIAL_CAPITAL.values()))
    # V5.1 포트폴리오 메트릭 자동 갱신
    port['metrics'] = _compute_portfolio_metrics(port)
    PORT_FILE.write_text(json.dumps(port, ensure_ascii=False, indent=2), encoding='utf-8')


def _is_duplicate_trade(ticker: str, open_time: str, close_time: str) -> bool:
    """이미 CSV에 기록된 (ticker, open_time, close_time) 조합인지 확인 — 중복 로그 방지"""
    if not TRADES_FILE.exists():
        return False
    try:
        with open(TRADES_FILE, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if (row.get('ticker') == ticker
                        and row.get('open_time') == open_time
                        and row.get('close_time') == close_time):
                    return True
    except Exception:
        pass
    return False


def _check_circuit_breaker(portfolio: dict, pos_data: dict = None) -> tuple:
    """V5.1 서킷브레이커: Daily(실현+미실현) / Weekly / Peak-Equity MDD

    Returns:
        (halted: bool, reason: str)
    """
    try:
        from config.settings import DAILY_LOSS_LIMIT, WEEKLY_LOSS_LIMIT, MDD_LIMIT
    except Exception:
        DAILY_LOSS_LIMIT  = -0.015
        WEEKLY_LOSS_LIMIT = -0.05
        MDD_LIMIT         = -0.10

    total_init = sum(INITIAL_CAPITAL.values())
    if total_init <= 0:
        return False, ''

    today_key = datetime.now().strftime('%Y-%m-%d')

    # ── 1. 당일 실현 손익 (paper_trades.csv) ────────────────────
    today_realized = 0.0
    try:
        if TRADES_FILE.exists():
            with open(TRADES_FILE, encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('close_time', '').startswith(today_key):
                        today_realized += float(row.get('pnl_krw', 0) or 0)
    except Exception:
        pass

    # ── 2. 미실현 손익 (오픈 포지션 현재가) ─────────────────────
    unrealized = 0.0
    if pos_data:
        for pos in pos_data.get('positions', []):
            try:
                price = _get_price(pos['ticker'], market=pos.get('market', ''))
                if price:
                    unrealized += (price - pos['entry']) / pos['entry'] * pos['size_krw']
            except Exception:
                pass

    # ── 3. 일일 손익 = 실현 + 미실현 ───────────────────────────
    daily_total = today_realized + unrealized
    daily_pct   = daily_total / total_init
    if daily_pct <= DAILY_LOSS_LIMIT:
        return True, (
            f"[CB-Daily] 일일 손익 {daily_pct*100:.2f}% "
            f"(실현 {today_realized:+,.0f} + 미실현 {unrealized:+,.0f}원) "
            f"— 한도 {DAILY_LOSS_LIMIT*100:.1f}% → 신규 진입 차단"
        )

    # ── 4. 주간 손익 (이번 주 월요일 00:00 이후 CSV) ────────────
    now = datetime.now()
    monday_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    weekly_pnl = 0.0
    try:
        if TRADES_FILE.exists():
            with open(TRADES_FILE, encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    ct = row.get('close_time', '')
                    try:
                        if datetime.fromisoformat(ct) >= monday_start:
                            weekly_pnl += float(row.get('pnl_krw', 0) or 0)
                    except Exception:
                        pass
    except Exception:
        pass
    weekly_pct = weekly_pnl / total_init
    if weekly_pct <= WEEKLY_LOSS_LIMIT:
        return True, (
            f"[CB-Weekly] 주간 손익 {weekly_pct*100:.2f}% "
            f"({weekly_pnl:+,.0f}원, {monday_start.strftime('%m/%d')}~) "
            f"— 한도 {WEEKLY_LOSS_LIMIT*100:.1f}% → 이번 주 신규 진입 차단"
        )

    # ── 5. MDD (Peak Equity 기준) ───────────────────────────────
    # current_equity = 가용자금 + 오픈포지션원금 + 미실현손익
    avail_cash = sum(portfolio.get('capital', {}).values())
    open_cost  = sum(p.get('size_krw', 0) for p in (pos_data or {}).get('positions', []))
    current_equity = avail_cash + open_cost + unrealized

    peak_equity = portfolio.get('peak_equity', total_init)
    if current_equity > peak_equity:
        peak_equity = current_equity
        portfolio['peak_equity'] = round(peak_equity, 0)

    mdd_pct = current_equity / peak_equity - 1 if peak_equity > 0 else 0
    if mdd_pct <= MDD_LIMIT:
        return True, (
            f"[CB-MDD] 최대낙폭 {mdd_pct*100:.2f}% "
            f"(현재 {current_equity/1e6:.2f}억 / 피크 {peak_equity/1e6:.2f}억) "
            f"— 한도 {MDD_LIMIT*100:.1f}% → 봇 자동 정지"
        )

    return False, ''


def _get_atr(ticker: str, market: str = '', period: int = 14) -> float | None:
    """V5.2 ATR(14) 계산 — True Range 기반 변동성 지표.

    일봉 데이터로 ATR을 계산하고 현재가 대비 비율(ATR%)로 반환한다.

    Returns:
        atr_pct: ATR / 현재가 (소수, 예: 0.03 = 3%)
        None:    데이터 부족 또는 조회 실패
    """
    yf_tk = YF_TICKER.get(ticker)
    if not yf_tk:
        return None
    try:
        df = yf.download(yf_tk, period='60d', interval='1d',
                         auto_adjust=True, progress=False)
        if df is None or len(df) < period + 2:
            return None
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)

        high  = df['High']
        low   = df['Low']
        close = df['Close']

        # True Range = max(H-L, |H-prevC|, |L-prevC|)
        import pandas as _pd
        prev_close = close.shift(1)
        tr = _pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)

        atr = float(tr.rolling(period).mean().iloc[-1])
        current_price = float(close.iloc[-1])

        if current_price > 0 and atr > 0:
            _PRICE_CACHE[ticker] = (current_price, datetime.now())  # 캐시 겸 업데이트
            return round(atr / current_price, 6)   # ATR as % of price
    except Exception:
        pass
    return None


def calc_risk_based_position_size(
    total_equity: float,
    entry_price: float,
    sl_price: float,
    risk_pct: float = None,
    max_position_krw: float = None,
    atr_pct: float = None,
) -> dict:
    """V5.2 Risk-based + ATR-based position sizing.

    실제 주문은 POSITION_SIZE(고정)를 사용하지만,
    이 함수가 반환하는 값을 로그에 기록해 참고한다.
    v5.3에서 실전 적용 여부 결정.

    공식:
        risk_krw     = total_equity * risk_pct       # 허용 손실 금액
        sl_based_krw = risk_krw / sl_pct             # SL 거리로 역산
        atr_based_krw= risk_krw / atr_pct            # ATR로 역산 (제공 시)

    Args:
        total_equity:     전체 평가 자산 (원)
        entry_price:      진입가
        sl_price:         손절가
        risk_pct:         거래당 허용 손실 비율 (기본: RISK_PER_TRADE_PCT=0.003)
        max_position_krw: 최대 포지션 상한
        atr_pct:          ATR% (_get_atr 반환값, None이면 ATR sizing 생략)

    Returns:
        dict:
            sl_based_krw  — SL 거리 기반 권장 포지션 (원)
            atr_based_krw — ATR 기반 권장 포지션 (원, atr_pct 있을 때만)
            recommended_krw — 최종 권장 (ATR 있으면 ATR 기준, 없으면 SL 기준)
            risk_krw      — 허용 손실 금액
            sl_pct        — SL 거리 (%)
            atr_pct_used  — 사용된 ATR% (없으면 0)
    """
    if risk_pct is None:
        risk_pct = RISK_PER_TRADE_PCT

    risk_krw = total_equity * risk_pct
    cap      = max_position_krw

    # SL 기반
    sl_pct_val = abs(entry_price - sl_price) / entry_price if entry_price > 0 else 0
    sl_based   = int(risk_krw / sl_pct_val) if sl_pct_val > 0 else 0
    if cap:
        sl_based = min(sl_based, int(cap))

    # ATR 기반
    atr_based = 0
    if atr_pct and atr_pct > 0:
        atr_based = int(risk_krw / atr_pct)
        if cap:
            atr_based = min(atr_based, int(cap))

    recommended = atr_based if atr_based > 0 else sl_based

    return {
        'sl_based_krw':   sl_based,
        'atr_based_krw':  atr_based,
        'recommended_krw': recommended,
        'risk_krw':        int(risk_krw),
        'sl_pct':          round(sl_pct_val * 100, 2),
        'atr_pct_used':    round((atr_pct or 0) * 100, 2),
    }


def _compute_portfolio_metrics(port: dict) -> dict:
    """V5.1 포트폴리오 메트릭: 전체 + 시장별 + 전략별 breakdown.

    Returns:
        dict with keys:
          overall: {total_trades, win_rate, profit_factor, expectancy_krw,
                    sharpe, max_drawdown_pct, avg_win_krw, avg_loss_krw}
          by_market: {KR: {...}, US: {...}, CRYPTO: {...}}
          by_strategy: {BB_SWING: {...}, MACD: {...}, ...}
    """
    import statistics as _stats

    def _calc_stats(pnls: list) -> dict:
        if not pnls:
            return {'trades': 0, 'win_rate': 0, 'profit_factor': 0,
                    'expectancy_krw': 0, 'avg_win_krw': 0, 'avg_loss_krw': 0}
        wins = [p for p in pnls if p > 0]
        loss = [p for p in pnls if p <= 0]
        total = len(pnls)
        wr = len(wins) / total * 100
        gw = sum(wins) if wins else 0
        gl = abs(sum(loss)) if loss else 0
        pf = round(gw / gl, 3) if gl > 0 else (float('inf') if gw > 0 else 0.0)
        avg_w = round(_stats.mean(wins), 0) if wins else 0
        avg_l = round(abs(_stats.mean(loss)), 0) if loss else 0
        exp = round(len(wins) / total * avg_w - len(loss) / total * avg_l, 0)
        return {
            'trades':         total,
            'win_rate':       round(wr, 1),
            'profit_factor':  pf,
            'expectancy_krw': exp,
            'avg_win_krw':    avg_w,
            'avg_loss_krw':   avg_l,
        }

    metrics: dict = {
        'overall':     {},
        'by_market':   {},
        'by_strategy': {},
    }
    if not TRADES_FILE.exists():
        return metrics

    all_pnls: list = []
    by_market: dict = {}
    by_strategy: dict = {}
    cum_equity = sum(INITIAL_CAPITAL.values())
    peak_eq = cum_equity
    max_dd  = 0.0

    try:
        rows = []
        with open(TRADES_FILE, encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))

        for row in rows:
            try:
                p = float(row.get('pnl_krw', 0) or 0)
                mkt = row.get('market', 'OTHER')
                strat = row.get('signal_type', row.get('timeframe', 'OTHER'))
                all_pnls.append(p)
                by_market.setdefault(mkt, []).append(p)
                by_strategy.setdefault(strat, []).append(p)
                # MDD 계산 (거래 순서 기반)
                cum_equity += p
                if cum_equity > peak_eq:
                    peak_eq = cum_equity
                dd = (cum_equity - peak_eq) / peak_eq if peak_eq > 0 else 0
                if dd < max_dd:
                    max_dd = dd
            except Exception:
                pass

        # Sharpe
        sharpe = 0.0
        if len(all_pnls) >= 2:
            avg_p = _stats.mean(all_pnls)
            std_p = _stats.stdev(all_pnls)
            sharpe = round(avg_p / std_p, 3) if std_p > 0 else 0.0

        overall = _calc_stats(all_pnls)
        overall['sharpe'] = sharpe
        overall['max_drawdown_pct'] = round(max_dd * 100, 2)
        metrics['overall'] = overall
        metrics['by_market']   = {k: _calc_stats(v) for k, v in by_market.items()}
        metrics['by_strategy'] = {k: _calc_stats(v) for k, v in by_strategy.items()}
    except Exception:
        pass
    return metrics


def _log_trade(row: dict):
    # 중복 체크: 같은 ticker+open_time+close_time 이미 기록됐으면 스킵
    if _is_duplicate_trade(row['ticker'], row['open_time'], row['close_time']):
        return
    write_header = not TRADES_FILE.exists()
    with open(TRADES_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=TRADES_HEADER)
        if write_header:
            w.writeheader()
        w.writerow(row)


# ── V5.3 성과 분석 엔진 ─────────────────────────────────────────────
def _compute_performance_report() -> dict:
    """V5.3 성과 분석: 30일/90일/전체 윈도우 × ticker별/전략별 breakdown.

    paper_trades.csv를 읽어 PF/Expectancy/MDD/Sharpe를 계산하고
    performance_report.json에 저장한다.

    Returns:
        dict: {generated_at, windows:{all,90d,30d}, by_ticker, by_strategy}
    """
    import statistics as _stats
    from datetime import timedelta as _td

    def _window_pnls(rows: list, days: int = None) -> list:
        """days=None → 전체 기간, 숫자 → 최근 N일"""
        cutoff = (datetime.now() - _td(days=days)) if days else None
        result = []
        for row in rows:
            if cutoff:
                try:
                    dt = datetime.strptime(row.get('close_time', '')[:19], '%Y-%m-%d %H:%M:%S')
                    if dt < cutoff:
                        continue
                except Exception:
                    pass
            try:
                result.append(float(row.get('pnl_krw', 0) or 0))
            except Exception:
                pass
        return result

    def _calc_metrics(pnls: list) -> dict:
        if not pnls:
            return {'trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0,
                    'expectancy_krw': 0, 'avg_win_krw': 0, 'avg_loss_krw': 0,
                    'sharpe': 0.0, 'max_drawdown_pct': 0.0}
        wins = [p for p in pnls if p > 0]
        loss = [p for p in pnls if p <= 0]
        n    = len(pnls)
        gw   = sum(wins) if wins else 0
        gl   = abs(sum(loss)) if loss else 0
        pf   = round(gw / gl, 3) if gl > 0 else (float('inf') if gw > 0 else 0.0)
        avg_w = round(_stats.mean(wins), 0) if wins else 0
        avg_l = round(abs(_stats.mean(loss)), 0) if loss else 0
        exp   = round(len(wins) / n * avg_w - len(loss) / n * avg_l, 0)
        # Sharpe (거래 단위, 무위험수익률 생략)
        sharpe = 0.0
        if len(pnls) >= 2:
            std_p = _stats.stdev(pnls)
            sharpe = round(_stats.mean(pnls) / std_p, 3) if std_p > 0 else 0.0
        # MDD (거래 순서 기반 누적 자본 곡선)
        eq = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            eq += p
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (eq - peak) / peak
                if dd < max_dd:
                    max_dd = dd
        return {
            'trades':           n,
            'win_rate':         round(len(wins) / n * 100, 1),
            'profit_factor':    pf,
            'expectancy_krw':   int(exp),
            'avg_win_krw':      int(avg_w),
            'avg_loss_krw':     int(avg_l),
            'sharpe':           sharpe,
            'max_drawdown_pct': round(max_dd * 100, 2),
        }

    report: dict = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'windows':      {},
        'by_ticker':    {},
        'by_strategy':  {},
    }

    if not TRADES_FILE.exists():
        _save_perf_report(report)
        return report

    try:
        with open(TRADES_FILE, encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
    except Exception:
        _save_perf_report(report)
        return report

    # ── 윈도우별 전체 집계 ──────────────────────────────────────────
    for label, days in [('all', None), ('90d', 90), ('30d', 30)]:
        report['windows'][label] = _calc_metrics(_window_pnls(rows, days))

    # ── ticker별 / 전략별 (전체 기간) ──────────────────────────────
    by_ticker:   dict = {}
    by_strategy: dict = {}
    for row in rows:
        try:
            p = float(row.get('pnl_krw', 0) or 0)
        except Exception:
            continue
        ticker = row.get('ticker', 'OTHER')
        strat  = row.get('signal_type') or row.get('timeframe') or 'OTHER'
        by_ticker.setdefault(ticker, []).append(p)
        by_strategy.setdefault(strat, []).append(p)

    report['by_ticker']   = {k: _calc_metrics(v) for k, v in by_ticker.items()}
    report['by_strategy'] = {k: _calc_metrics(v) for k, v in by_strategy.items()}

    _save_perf_report(report)
    return report


def _save_perf_report(report: dict) -> None:
    """performance_report.json 저장."""
    try:
        with open(PERF_REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── V6.0 마켓 레짐 감지 + 전략 로테이션 제안 ─────────────────────────

# 레짐별 전략 우선순위 (실제 코드 자동 적용 금지, 제안 참고용)
ROTATION_STRATEGY: dict = {
    'TRENDING': {
        'US':     ['MACD', 'BB_MOM', 'SUPERTREND', 'BB_REVERSAL', 'BB_SWING'],
        'KR':     ['MOMENTUM', 'MACD', 'BB_SWING', 'GAPGO'],
        'CRYPTO': ['FVG_OB_4H', 'FVG_OB_15M'],
        'reason': 'SPY 200MA 위 + QQQ 50MA 상향 + VIX<20 → 추세추종 우선',
    },
    'SIDEWAYS': {
        'US':     ['BB_REVERSAL', 'BB_MOM', 'SUPERTREND', 'MACD', 'BB_SWING'],
        'KR':     ['BB_SWING', 'BB_REVERSAL', 'MACD', 'MOMENTUM'],
        'CRYPTO': ['FVG_OB_15M', 'FVG_OB_4H'],
        'reason': 'SPY 200MA 근접(±2%) OR QQQ 기울기 완만 → 평균회귀 우선',
    },
    'RISK_OFF': {
        'US':     ['SUPERTREND', 'BB_REVERSAL', 'BB_SWING', 'MACD', 'BB_MOM'],
        'KR':     ['BB_SWING', 'BB_REVERSAL', 'MOMENTUM', 'MACD'],
        'CRYPTO': [],  # RISK_OFF 시 CRYPTO 신규 진입 자제 권고
        'reason': 'SPY 200MA 아래(-2%↓) OR VIX>30 → 방어적 전략 + CRYPTO 자제',
    },
}


def _detect_market_regime() -> dict:
    """V6.1 마켓 레짐 감지: TRENDING / SIDEWAYS / RISK_OFF.

    사용 지표 (4가지):
      - SPY:   현재가 vs 200MA (추세 방향)        → 점수 0~2
      - QQQ:   50MA 5일 기울기 (모멘텀 강도)      → 점수 0~1
      - VIX:   변동성 수준 (공포 지수)            → 점수 0~2
      - 시장 폭: US 유니버스 중 50MA 위 비율      → 점수 0~1
      - BTC 도미넌스: BTC/(BTC+ETH+SOL) 추정     → 점수 0~1 (보조)

    점수 합산 (0~7점):
      TRENDING  : ≥5점
      SIDEWAYS  : 2~4점
      RISK_OFF  : ≤1점  또는 VIX≥30 또는 SPY≤-2% (하드 트리거)

    Returns:
        dict:
          regime          — 'TRENDING' | 'SIDEWAYS' | 'RISK_OFF' | 'UNKNOWN'
          spy_vs_200ma    — SPY 200MA 대비 %
          qqq_slope_5d    — QQQ 50MA 5일 기울기 %
          vix_level       — VIX 수준
          breadth_pct     — US 유니버스 50MA 위 비율 (0~1)
          btc_dominance   — BTC 추정 도미넌스 (0~1)
          regime_score    — 합산 점수 (0~7)
          detected_at     — 감지 시각
    """
    import yfinance as _yf
    import pandas as _pd

    result = {
        'regime':         'UNKNOWN',
        'spy_vs_200ma':   0.0,
        'qqq_slope_5d':   0.0,
        'vix_level':      0.0,
        'breadth_pct':    0.0,
        'btc_dominance':  0.0,
        'regime_score':   0,
        'detected_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    score = 0

    try:
        # ── 1) SPY 200MA ──────────────────────────────────────────
        spy_df = _yf.download('SPY', period='220d', interval='1d',
                               auto_adjust=True, progress=False)
        if spy_df is None or len(spy_df) < 205:
            result['error'] = 'SPY data insufficient'
            return result
        if hasattr(spy_df.columns, 'levels'):
            spy_df.columns = spy_df.columns.droplevel(1)
        spy_close  = spy_df['Close']
        spy_price  = float(spy_close.iloc[-1])
        spy_200ma  = float(spy_close.rolling(200).mean().iloc[-1])
        spy_vs_200 = round((spy_price / spy_200ma - 1) * 100, 2)
        result['spy_vs_200ma'] = spy_vs_200

        if spy_vs_200 >= 3.0:
            score += 2
        elif spy_vs_200 >= 0.0:
            score += 1
        # ≤ -2%이면 하드 RISK_OFF → 나중에 판정

        # ── 2) QQQ 50MA 기울기 ───────────────────────────────────
        qqq_df = _yf.download('QQQ', period='70d', interval='1d',
                               auto_adjust=True, progress=False)
        if qqq_df is not None and len(qqq_df) >= 55:
            if hasattr(qqq_df.columns, 'levels'):
                qqq_df.columns = qqq_df.columns.droplevel(1)
            qqq_ma = qqq_df['Close'].rolling(50).mean()
            qqq_slope = round((float(qqq_ma.iloc[-1]) / float(qqq_ma.iloc[-6]) - 1) * 100, 3)
            result['qqq_slope_5d'] = qqq_slope
            if qqq_slope >= 0.3:
                score += 1

        # ── 3) VIX ───────────────────────────────────────────────
        vix_df = _yf.download('^VIX', period='5d', interval='1d',
                               auto_adjust=True, progress=False)
        if vix_df is not None and len(vix_df) > 0:
            if hasattr(vix_df.columns, 'levels'):
                vix_df.columns = vix_df.columns.droplevel(1)
            vix_level = round(float(vix_df['Close'].iloc[-1]), 2)
            result['vix_level'] = vix_level
            if vix_level < 18:
                score += 2
            elif vix_level < 25:
                score += 1
            # ≥30이면 하드 RISK_OFF

    except Exception as e:
        result['error'] = str(e)
        return result

    # ── 4) 시장 폭: US 유니버스 종목 중 50MA 위 비율 ─────────────
    try:
        us_tickers   = list(YF_TICKER.values())[:10]   # 최대 10개만
        above_count  = 0
        checked      = 0
        if us_tickers:
            bulk = _yf.download(us_tickers, period='60d', interval='1d',
                                auto_adjust=True, progress=False)
            close_data = bulk['Close'] if 'Close' in bulk.columns else bulk
            for tk in us_tickers:
                try:
                    ser = close_data[tk].dropna()
                    if len(ser) >= 50:
                        ma50 = float(ser.rolling(50).mean().iloc[-1])
                        if float(ser.iloc[-1]) > ma50:
                            above_count += 1
                        checked += 1
                except Exception:
                    pass
        if checked > 0:
            breadth = round(above_count / checked, 3)
            result['breadth_pct'] = breadth
            if breadth >= 0.7:
                score += 1
    except Exception:
        pass   # 시장 폭 실패 시 점수 추가 없이 계속

    # ── 5) BTC 도미넌스 추정 (보조 지표) ─────────────────────────
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'SOL-USD']
        # 간단한 근사 공급량 (실물 순환 공급량 추정치)
        approx_supply  = {'BTC-USD': 19_700_000, 'ETH-USD': 120_000_000,
                          'SOL-USD': 460_000_000}
        crypto_df = _yf.download(crypto_tickers, period='2d', interval='1d',
                                 auto_adjust=True, progress=False)
        if crypto_df is not None and len(crypto_df) > 0:
            close_c = crypto_df['Close'] if 'Close' in crypto_df.columns else crypto_df
            mc = {}
            for tk in crypto_tickers:
                try:
                    price = float(close_c[tk].dropna().iloc[-1])
                    mc[tk] = price * approx_supply.get(tk, 0)
                except Exception:
                    mc[tk] = 0
            total_mc = sum(mc.values())
            if total_mc > 0:
                btc_dom = round(mc.get('BTC-USD', 0) / total_mc, 4)
                result['btc_dominance'] = btc_dom
                # BTC 도미넌스 높으면(>0.6) 알트 리스크 선호 낮음
                if btc_dom < 0.55:   # 알트 리스크 선호 → 추세 신호 강화
                    score += 1
    except Exception:
        pass   # BTC 도미넌스 실패 시 계속

    result['regime_score'] = score

    # ── 레짐 판정 (하드 트리거 우선) ─────────────────────────────
    vix_lv  = result['vix_level']
    spy_vs  = result['spy_vs_200ma']
    if spy_vs <= -2.0 or vix_lv >= 30:
        regime = 'RISK_OFF'
    elif score >= 5:
        regime = 'TRENDING'
    elif score <= 1:
        regime = 'RISK_OFF'
    else:
        regime = 'SIDEWAYS'

    result['regime'] = regime

    # ── 레짐 히스토리 저장 ────────────────────────────────────────
    _append_regime_history(result)

    return result


def _append_regime_history(regime_data: dict) -> None:
    """V6.1 레짐 히스토리 로그: logs/regime_history.json에 누적 저장."""
    history_file = LOG_DIR / 'regime_history.json'
    try:
        history: list = []
        if history_file.exists():
            history = json.loads(history_file.read_text(encoding='utf-8'))
        history.append(regime_data)
        # 최근 200개만 유지
        if len(history) > 200:
            history = history[-200:]
        history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                                encoding='utf-8')
    except Exception:
        pass


def _generate_capital_allocation_proposal(regime_data: dict) -> dict | None:
    """V6.2 동적 자본 배분 제안 (PENDING, 절대 자동 적용 금지).

    성과 리포트(30d 시장별) + 레짐 데이터를 결합하여
    KR/US/CRYPTO 자본 배분 비율 변경안을 제안한다.

    원칙:
      - 성과 우수(WR↑/PF↑) 시장에 자본 집중 제안
      - RISK_OFF 시 CRYPTO 배분 축소 제안
      - 제안 범위: ±20%p 이내 조정 (과도한 집중 방지)
      - 총합은 항상 100% 유지

    Returns:
        dict: 배분 제안 (PENDING), None이면 데이터 부족
    """
    regime = regime_data.get('regime', 'UNKNOWN')

    # 현재 배분 비율
    total_init = sum(INITIAL_CAPITAL.values())
    current_alloc = {k: round(v / total_init * 100, 1) for k, v in INITIAL_CAPITAL.items()}

    # 성과 리포트(30d 시장별) 로드
    by_market_30d: dict = {}
    if PERF_REPORT_FILE.exists():
        try:
            with open(PERF_REPORT_FILE, encoding='utf-8') as f:
                perf = json.load(f)
            # by_market은 전체 기간 → windows.30d 데이터 없음
            # 30d 전체 지표를 참고하여 시장별 추정
            by_market_30d = perf.get('by_market', {})
        except Exception:
            pass

    if not by_market_30d:
        return None   # 성과 데이터 없으면 제안 불가

    # ── 시장별 성과 점수 계산 ────────────────────────────────────
    market_scores: dict = {}
    for mkt in ['KR', 'US', 'CRYPTO']:
        stats = by_market_30d.get(mkt, {})
        trades = stats.get('trades', 0)
        if trades == 0:
            market_scores[mkt] = 0
            continue
        wr  = stats.get('win_rate', 0)
        pf  = min(stats.get('profit_factor', 0), 5.0)   # 상한 5.0 (inf 방지)
        exp = stats.get('expectancy_krw', 0)
        # 점수 = WR 가중 + PF 가중 + Expectancy 부호
        score = (wr / 100 * 0.4) + (min(pf, 5) / 5 * 0.4) + (0.2 if exp > 0 else 0)
        market_scores[mkt] = round(score, 4)

    # ── 레짐 오버라이드 ──────────────────────────────────────────
    if regime == 'RISK_OFF':
        market_scores['CRYPTO'] = market_scores.get('CRYPTO', 0) * 0.3  # CRYPTO 대폭 축소
    elif regime == 'TRENDING':
        market_scores['US'] = market_scores.get('US', 0) * 1.2  # US 가중 (추세 추종)

    # ── 제안 배분 계산 ───────────────────────────────────────────
    total_score = sum(market_scores.values())
    if total_score <= 0:
        # 성과 데이터 없거나 전부 0 → 균등 배분 제안
        proposed_pct = {k: 33.3 for k in ['KR', 'US', 'CRYPTO']}
        proposed_pct['US'] = 100 - 33.3 * 2  # 반올림 보정
    else:
        raw_pct = {k: v / total_score * 100 for k, v in market_scores.items()}
        # ±20%p 범위로 클리핑 (극단적 쏠림 방지)
        proposed_pct: dict = {}
        for mkt in ['KR', 'US', 'CRYPTO']:
            curr = current_alloc.get(mkt, 33.3)
            raw  = raw_pct.get(mkt, curr)
            clamped = max(curr - 20, min(curr + 20, raw))
            proposed_pct[mkt] = round(clamped, 1)
        # 합계 100% 정규화
        total_p = sum(proposed_pct.values())
        if total_p > 0:
            proposed_pct = {k: round(v / total_p * 100, 1) for k, v in proposed_pct.items()}

    # 현재 대비 변화 계산
    diff_pct = {k: round(proposed_pct.get(k, 0) - current_alloc.get(k, 0), 1)
                for k in ['KR', 'US', 'CRYPTO']}

    return {
        'proposed_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status':         'PENDING',
        'type':           'CAPITAL_ALLOCATION',
        'regime':         regime,
        'current_alloc':  current_alloc,
        'proposed_alloc': proposed_pct,
        'diff_pct':       diff_pct,
        'market_scores':  market_scores,
        'note':           '자동 적용 금지 — INITIAL_CAPITAL/POSITION_SIZE 수동 수정 필요',
    }


def _generate_rotation_proposal(regime_data: dict) -> dict | None:
    """V6.0 전략 로테이션 제안 생성 (PENDING, 절대 자동 적용 금지).

    성과 리포트(30d)와 레짐 판정을 결합하여 전략 우선순위 변경안을 생성한다.
    실제 코드(_KR/US_TICKER_STRATEGY)는 절대 변경하지 않는다.

    Returns:
        dict: 제안 내용 (run_master_loop.py → strategy_proposals.json에 저장)
        None: 레짐 감지 실패
    """
    regime = regime_data.get('regime', 'UNKNOWN')
    if regime == 'UNKNOWN':
        return None

    rotation = ROTATION_STRATEGY.get(regime, {})

    # 최근 30일 성과 요약 첨부
    perf_summary: dict = {}
    if PERF_REPORT_FILE.exists():
        try:
            with open(PERF_REPORT_FILE, encoding='utf-8') as f:
                perf = json.load(f)
            w30 = perf.get('windows', {}).get('30d', {})
            perf_summary = {
                'trades_30d':   w30.get('trades', 0),
                'win_rate_30d': w30.get('win_rate', 0),
                'pf_30d':       w30.get('profit_factor', 0),
                'exp_30d':      w30.get('expectancy_krw', 0),
            }
        except Exception:
            pass

    return {
        'proposed_at':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status':       'PENDING',
        'type':         'STRATEGY_ROTATION',
        'regime':       regime,
        'regime_data':  regime_data,
        'perf_summary': perf_summary,
        'proposal': {
            'US_priority':     rotation.get('US', []),
            'KR_priority':     rotation.get('KR', []),
            'CRYPTO_priority': rotation.get('CRYPTO', []),
            'reason':          rotation.get('reason', ''),
        },
        'note': '자동 적용 금지 — Claude Code 논의 후 수동 승인 필요',
    }


# ── V7.0 AI 운영 에이전트 ────────────────────────────────────────

def _detect_anomalies(pos_data: dict, portfolio: dict) -> list[dict]:
    """V7.0 리스크 이상 감지 — 거래 실행 없이 분석만 수행.

    감지 항목:
      1. 연속 손실 3회 이상 (최근 거래 기준)
      2. 섹터 집중 위험 (MAX_SECTOR_POSITIONS 초과 포지션)
      3. 장기 미청산 포지션 (5일 이상 보유)
      4. 자본 대비 과도한 미실현 손실 (단일 포지션 -5% 이상)

    Returns:
        list of {type, severity, message, detail}
    """
    anomalies = []
    now = datetime.now()

    # ── 1. 연속 손실 감지 ────────────────────────────────────────
    if TRADES_FILE.exists():
        try:
            with open(TRADES_FILE, encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
            recent = rows[-10:] if len(rows) >= 10 else rows
            streak = 0
            for row in reversed(recent):
                if (row.get('result') or '').upper() == 'LOSS':
                    streak += 1
                else:
                    break
            if streak >= 3:
                anomalies.append({
                    'type':     'CONSECUTIVE_LOSS',
                    'severity': 'HIGH' if streak >= 5 else 'MEDIUM',
                    'message':  f'연속 손실 {streak}회 감지 — 전략 점검 권고',
                    'detail':   {'streak': streak},
                })
        except Exception:
            pass

    # ── 2. 섹터 집중 위험 ────────────────────────────────────────
    try:
        from config.settings import MAX_SECTOR_POSITIONS as _max_sec
    except ImportError:
        _max_sec = 2

    sector_count: dict = {}
    for pos in pos_data.get('positions', []):
        mkt    = pos.get('market', '')
        ticker = pos.get('ticker', '')
        if mkt == 'CRYPTO':
            continue
        sector = SECTOR_MAP.get(ticker, 'OTHER')
        sector_count[sector] = sector_count.get(sector, 0) + 1

    for sector, cnt in sector_count.items():
        if cnt > _max_sec:
            anomalies.append({
                'type':     'SECTOR_CONCENTRATION',
                'severity': 'MEDIUM',
                'message':  f'섹터 집중 위험: {sector} 섹터 {cnt}포지션 (최대{_max_sec})',
                'detail':   {'sector': sector, 'count': cnt, 'max': _max_sec},
            })

    # ── 3. 장기 미청산 포지션 (5일↑) ────────────────────────────
    for pos in pos_data.get('positions', []):
        try:
            open_dt = datetime.strptime(pos.get('open_time', '')[:19], '%Y-%m-%d %H:%M:%S')
            hold_days = (now - open_dt).days
            if hold_days >= 5:
                anomalies.append({
                    'type':     'LONG_HOLD',
                    'severity': 'LOW',
                    'message':  f"{pos.get('name', pos['ticker'])} {hold_days}일 보유 — TP/SL 점검",
                    'detail':   {'ticker': pos['ticker'], 'hold_days': hold_days},
                })
        except Exception:
            pass

    # ── 4. 단일 포지션 대형 미실현 손실 (-5% 이하) ───────────────
    for pos in pos_data.get('positions', []):
        try:
            price = _PRICE_CACHE.get(pos['ticker'], (None,))[0]
            if price and pos.get('entry'):
                pnl_pct = (price - float(pos['entry'])) / float(pos['entry']) * 100
                if pnl_pct <= -5.0:
                    anomalies.append({
                        'type':     'LARGE_LOSS_POSITION',
                        'severity': 'HIGH',
                        'message':  f"{pos.get('name', pos['ticker'])} 미실현 {pnl_pct:.1f}% — SL 재확인",
                        'detail':   {'ticker': pos['ticker'], 'pnl_pct': round(pnl_pct, 2)},
                    })
        except Exception:
            pass

    return anomalies


def _generate_daily_report(pos_data: dict, portfolio: dict) -> dict:
    """V7.0 일일 AI 운영 리포트 생성 — 거래 실행 없음, 분석 전용.

    portfolio, performance_report, regime_history, open_positions를 종합하여
    일일 요약 리포트를 생성하고 logs/journal/에 저장한다.

    Returns:
        dict: {date, summary, performance, regime, anomalies, open_positions, recommendations}
    """
    today = now = datetime.now()
    date_str = today.strftime('%Y-%m-%d')

    # ── 포트폴리오 요약 ───────────────────────────────────────────
    total_init = sum(INITIAL_CAPITAL.values())
    total_now  = sum(portfolio.get('capital', {}).values())
    total_pnl  = sum(portfolio.get('realized_pnl', {}).values())
    total_tr   = portfolio.get('total_trades', 0)
    wins       = portfolio.get('wins', 0)
    wr         = round(wins / total_tr * 100, 1) if total_tr > 0 else 0

    summary = {
        'total_initial_krw': total_init,
        'total_current_krw': total_now,
        'total_realized_pnl': total_pnl,
        'return_pct': round((total_now - total_init) / total_init * 100, 2) if total_init > 0 else 0,
        'total_trades': total_tr,
        'win_rate': wr,
        'open_positions': len(pos_data.get('positions', [])),
    }

    # ── 성과 리포트 (30d) ────────────────────────────────────────
    performance = {}
    if PERF_REPORT_FILE.exists():
        try:
            with open(PERF_REPORT_FILE, encoding='utf-8') as f:
                perf = json.load(f)
            performance = {
                'all': perf.get('windows', {}).get('all', {}),
                '30d': perf.get('windows', {}).get('30d', {}),
                'by_market':   perf.get('by_market', {}),
                'by_strategy': perf.get('by_strategy', {}),
            }
        except Exception:
            pass

    # ── 최신 레짐 ────────────────────────────────────────────────
    latest_regime: dict = {}
    history_file = LOG_DIR / 'regime_history.json'
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding='utf-8'))
            if history:
                latest_regime = history[-1]
        except Exception:
            pass

    # ── 이상 감지 ────────────────────────────────────────────────
    anomalies = _detect_anomalies(pos_data, portfolio)

    # ── 오픈 포지션 요약 ─────────────────────────────────────────
    open_summary = []
    for pos in pos_data.get('positions', []):
        entry = float(pos.get('entry', 0))
        price = _PRICE_CACHE.get(pos['ticker'], (None,))[0]
        pnl_pct = round((price - entry) / entry * 100, 2) if (price and entry > 0) else None
        open_summary.append({
            'ticker':    pos.get('ticker', ''),
            'name':      pos.get('name', ''),
            'market':    pos.get('market', ''),
            'timeframe': pos.get('timeframe', ''),
            'entry':     entry,
            'current':   price,
            'pnl_pct':   pnl_pct,
        })

    # ── 권고사항 생성 ────────────────────────────────────────────
    recommendations = []
    w30 = performance.get('30d', {})
    if w30.get('profit_factor', 0) < 1.0 and w30.get('trades', 0) >= 5:
        recommendations.append('30일 PF < 1.0 — 전략 재검토 필요')
    if w30.get('max_drawdown_pct', 0) < -15:
        recommendations.append(f"30일 MDD {w30['max_drawdown_pct']:.1f}% — 포지션 크기 축소 고려")
    if latest_regime.get('regime') == 'RISK_OFF':
        recommendations.append('RISK_OFF 레짐 — 신규 진입 최소화, CRYPTO 자제')
    for a in anomalies:
        if a['severity'] == 'HIGH':
            recommendations.append(f"[긴급] {a['message']}")

    report = {
        'generated_at':    now.strftime('%Y-%m-%d %H:%M:%S'),
        'date':            date_str,
        'summary':         summary,
        'performance':     performance,
        'regime':          latest_regime,
        'anomalies':       anomalies,
        'open_positions':  open_summary,
        'recommendations': recommendations,
    }

    # 저장
    journal_dir = LOG_DIR / 'journal'
    journal_dir.mkdir(exist_ok=True)
    report_path = journal_dir / f'{date_str}-ai_report.json'
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return report


# ── 현재가 캐시 (2분 TTL — 미실현손익 중복 조회 방지) ──────────────
_PRICE_CACHE: dict = {}   # {ticker: (price, timestamp)}
_PRICE_CACHE_TTL = 120    # seconds

# ── 현재가 조회 ──────────────────────────────────────────────────
# 우선순위: KR → KIS API, CRYPTO → Upbit, US/나머지 → yfinance
def _get_price(ticker: str, market: str = '') -> float | None:
    """현재가 조회. 시장별 최적 소스 사용. 2분 캐시 적용."""
    cached = _PRICE_CACHE.get(ticker)
    if cached:
        price, ts = cached
        if (datetime.now() - ts).total_seconds() < _PRICE_CACHE_TTL:
            return price
    # KR: KIS API 1순위
    if market == 'KR' or (not market and ticker.isdigit()):
        try:
            from core.kis_trader import get_price as _kis_price
            p = _kis_price(ticker)
            if p and p > 0:
                _PRICE_CACHE[ticker] = (float(p), datetime.now())
                return float(p)
        except Exception:
            pass

    # CRYPTO: Upbit 1순위
    if market == 'CRYPTO' or (not market and not ticker.isdigit() and '.' not in ticker and len(ticker) <= 5):
        try:
            import pyupbit
            p = pyupbit.get_current_price(f'KRW-{ticker}')
            if p and p > 0:
                _PRICE_CACHE[ticker] = (float(p), datetime.now())
                return float(p)
        except Exception:
            pass

    # yfinance fallback (US + 위 실패 시)
    yf_tk = YF_TICKER.get(ticker)
    if not yf_tk:
        return None
    try:
        df = yf.download(yf_tk, period='1d', interval='5m',
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        p = float(df['Close'].iloc[-1])
        _PRICE_CACHE[ticker] = (p, datetime.now())
        return p
    except Exception:
        return None


# ── TP 연장 전략 헬퍼 ─────────────────────────────────────────────

def _check_bearish_choch_15m(yf_tk: str) -> bool:
    """15m 베어리시 CHoCH(구조 전환) 감지.

    최근 15m 캔들에서 Lower High + Lower Low 구조 형성 여부.
    True 반환 시 즉시 청산 권고.
    """
    try:
        df = yf.download(yf_tk, period='1d', interval='15m',
                         auto_adjust=True, progress=False)
        if df is None or len(df) < 6:
            return False
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        highs = df['High'].values
        lows  = df['Low'].values
        # 최근 3봉: Lower High + Lower Low = 베어리시 CHoCH
        lh = highs[-1] < highs[-2] < highs[-3]
        ll = lows[-1]  < lows[-2]  < lows[-3]
        return bool(lh and ll)
    except Exception:
        return False


def _check_ema_align_15m(yf_tk: str) -> bool:
    """15m EMA 정렬 확인 (단기>중기>장기 = 상승 정렬).

    EMA5 > EMA20 > EMA60 이면 True.
    """
    try:
        df = yf.download(yf_tk, period='5d', interval='15m',
                         auto_adjust=True, progress=False)
        if df is None or len(df) < 60:
            return False
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        c = df['Close']
        e5  = float(c.ewm(span=5,  adjust=False).mean().iloc[-1])
        e20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        e60 = float(c.ewm(span=60, adjust=False).mean().iloc[-1])
        return e5 > e20 > e60
    except Exception:
        return False


def _check_15m_rsi(yf_tk: str, threshold: float = 50.0) -> bool:
    """15m RSI(14) > threshold 확인."""
    try:
        df = yf.download(yf_tk, period='5d', interval='15m',
                         auto_adjust=True, progress=False)
        if df is None or len(df) < 20:
            return False
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        c = df['Close']
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs   = gain / loss.replace(0, float('nan'))
        rsi  = float((100 - 100 / (1 + rs)).iloc[-1])
        return rsi > threshold
    except Exception:
        return False


def _check_tp_extension(pos: dict, price: float) -> dict | None:
    """TP 도달 시 연장 여부 판단.

    일봉 3조건 + 15m 3조건 체크.
    TP1→TP2: 4/6 이상, TP2→TP3: 5/6 이상.

    Returns:
        None: 연장 불가 → 현재 TP에서 청산
        dict: {'new_tp': float, 'new_sl': float, 'stage': int, 'reason': str}
    """
    stage     = pos.get('tp_stage', 1)
    entry     = pos['entry']
    tp_range  = pos['tp'] - entry          # TP1 기준 range
    yf_tk     = YF_TICKER.get(pos['ticker'], '')
    market    = pos.get('market', '')
    tf        = pos.get('timeframe', 'daily')

    # TP3 도달 → 무조건 청산 (연장 없음)
    if stage >= 3:
        return None

    # ── 장 마감 시간 체크 (KR: 15:20 이후 연장 불가) ──
    now_h = datetime.now().hour
    now_m = datetime.now().minute
    if market == 'KR' and (now_h > 15 or (now_h == 15 and now_m >= 20)):
        return None

    # ── 일봉 3조건 ──────────────────────────────────────
    score = 0
    reasons = []

    # 조건1: 일봉 RSI < 75
    try:
        df_d = yf.download(yf_tk, period='60d', interval='1d',
                           auto_adjust=True, progress=False)
        if df_d is not None and len(df_d) >= 14:
            if hasattr(df_d.columns, 'levels'):
                df_d.columns = df_d.columns.droplevel(1)
            c = df_d['Close']
            delta = c.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs   = gain / loss.replace(0, float('nan'))
            rsi  = float((100 - 100 / (1 + rs)).iloc[-1])
            if rsi < 75:
                score += 1
                reasons.append(f'RSI={rsi:.0f}<75')
    except Exception:
        pass

    # 조건2: 일봉 MACD 골든크로스 유지
    try:
        if df_d is not None and len(df_d) >= 26:
            c = df_d['Close']
            macd  = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
            signal = macd.ewm(span=9, adjust=False).mean()
            if float(macd.iloc[-1]) > float(signal.iloc[-1]):
                score += 1
                reasons.append('MACD>Signal')
    except Exception:
        pass

    # 조건3: 오늘 양봉 (Close > Open)
    try:
        if df_d is not None and len(df_d) >= 1:
            if hasattr(df_d.columns, 'levels'):
                pass
            if float(df_d['Close'].iloc[-1]) > float(df_d['Open'].iloc[-1]):
                score += 1
                reasons.append('양봉')
    except Exception:
        pass

    # ── 15m 3조건 (daily/4H 포지션만 적용) ──────────────
    if tf in ('daily', '4H') and yf_tk:
        # 조건4: 15m EMA 정렬
        if _check_ema_align_15m(yf_tk):
            score += 1
            reasons.append('15m_EMA정렬')

        # 조건5: 15m 베어리시 CHoCH 없음 (이건 필수 — CHoCH 있으면 즉시 거부)
        has_choch = _check_bearish_choch_15m(yf_tk)
        if not has_choch:
            score += 1
            reasons.append('15m_CHoCH없음')
        else:
            # CHoCH 발생 → 점수 무관하게 즉시 청산
            return None

        # 조건6: 15m RSI > 50
        if _check_15m_rsi(yf_tk, threshold=50.0):
            score += 1
            reasons.append('15m_RSI>50')

    # ── 연장 기준 ────────────────────────────────────────
    min_score = 4 if stage == 1 else 5   # TP1→TP2: 4/6, TP2→TP3: 5/6
    if score < min_score:
        return None

    new_stage = stage + 1
    # 원래 R(TP1 range) 복원: 현재 tp_range는 TP_stage/entry 누적값이므로 stage로 나눔
    # 예) stage=1: range = (TP1-entry)/1 = R
    #     stage=2: range = (TP2-entry)/2 = 2R/2 = R
    original_r = (pos['tp'] - entry) / stage
    new_sl     = pos['tp']              # SL → 현재 TP로 올림 (수익 확보)
    new_tp     = pos['tp'] + original_r # TP → 다음 단계 (항상 동일 R 추가)
    return {
        'new_tp':  round(new_tp, 4),
        'new_sl':  round(new_sl, 4),
        'stage':   new_stage,
        'score':   score,
        'reason':  f"TP{stage}→TP{new_stage} 연장 ({score}/6: {', '.join(reasons)})",
    }


# ── SL/TP 체크 ───────────────────────────────────────────────────
def check_positions(pos_data: dict, portfolio: dict) -> list:
    """오픈 포지션 SL/TP 도달 여부 체크, 청산 처리"""
    closed = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    remaining = []

    for pos in pos_data.get('positions', []):
        ticker  = pos['ticker']
        market  = pos['market']
        entry   = pos['entry']
        sl      = pos['sl']
        tp      = pos['tp']
        size    = pos['size_krw']
        open_dt = datetime.fromisoformat(pos['open_time'])
        hold_min = int((datetime.now() - open_dt).total_seconds() / 60)

        price = _get_price(ticker, market=market)
        if price is None:
            remaining.append(pos)
            continue

        reason = None
        exit_price = price

        # ── 15m 베어리시 CHoCH 감지 → 조기 청산 ─────────────
        yf_tk_pos = YF_TICKER.get(ticker, '')
        if pos.get('tp_stage', 1) >= 2 and yf_tk_pos:
            if _check_bearish_choch_15m(yf_tk_pos):
                reason = 'CHOCH_EXIT'
                exit_price = price
                print(f"    [CHoCH청산] {pos.get('name', ticker)} — 15m 베어리시 구조전환 감지")

        if not reason and price <= sl:
            reason = 'SL'
            exit_price = sl
        elif not reason and price >= tp:
            # ── TP 도달: 연장 여부 판단 ──────────────────────
            ext = _check_tp_extension(pos, price)
            if ext:
                # 연장: SL 올리고 TP 갱신, 포지션 유지
                pos['sl']       = ext['new_sl']
                pos['tp']       = ext['new_tp']
                pos['tp_stage'] = ext['stage']
                print(f"    [TP연장] {pos.get('name', ticker)} | "
                      f"{ext['reason']} | 새SL={ext['new_sl']:,.0f} 새TP={ext['new_tp']:,.0f}")
                remaining.append(pos)
                continue
            else:
                reason = f"TP{pos.get('tp_stage', 1)}"
                exit_price = tp
        elif not reason:
            # 타임프레임별 보유 한도
            tf = pos.get('timeframe', '15m')
            if tf in ('daily', '4H'):
                max_hold_min = 15 * 24 * 60   # 스윙/4H: 최대 15일
            else:
                max_hold_min = 32 * 15         # 단타: 32봉 × 15분
            if hold_min >= max_hold_min:
                reason = 'MAX_HOLD'

        if reason:
            pnl_pct = (exit_price - entry) / entry * 100
            pnl_krw = size * pnl_pct / 100
            win = pnl_pct > 0

            portfolio['capital'][market] = portfolio['capital'].get(market, 0) + size + pnl_krw
            portfolio['realized_pnl'][market] = portfolio['realized_pnl'].get(market, 0) + pnl_krw
            portfolio['total_trades'] = portfolio.get('total_trades', 0) + 1
            if win:
                portfolio['wins'] = portfolio.get('wins', 0) + 1
            else:
                portfolio['losses'] = portfolio.get('losses', 0) + 1

            row = {
                'open_time':       pos['open_time'],
                'close_time':      now_str,
                'ticker':          ticker,
                'name':            pos.get('name', ticker),
                'market':          market,
                'timeframe':       pos.get('timeframe', '15m'),
                'signal_type':     pos.get('signal_type', ''),
                'entry':           round(entry, 4),
                'exit':            round(exit_price, 4),
                'sl':              round(sl, 4),
                'tp':              round(tp, 4),
                'size_krw':        round(size),
                'pnl_pct':         round(pnl_pct, 2),
                'pnl_krw':         round(pnl_krw),
                'result':          'WIN' if win else 'LOSS',
                'close_reason':    reason,
                'tp_stage':        pos.get('tp_stage', 1),
                'quality_score':   pos.get('quality_score', 0),
                'quality_tags':    pos.get('quality_tags', ''),
                'hold_minutes':    hold_min,
                'entry_hour_kst':  pos.get('entry_hour_kst', 0),
                'vol_ratio':       pos.get('vol_ratio', 0),
                'has_vol_spike':   pos.get('has_vol_spike', False),
                'has_liq_sweep':   pos.get('has_liq_sweep', False),
                'has_choch':       pos.get('has_choch', False),
                'has_body_in_zone':pos.get('has_body_in_zone', False),
                'has_pinbar':      pos.get('has_pinbar', False),
                'has_ema_align':   pos.get('has_ema_align', False),
                'has_fresh_zone':  pos.get('has_fresh_zone', False),
            }
            _log_trade(row)
            closed.append(row)

            # 당일 청산 티커 기록 (SL/TP/MAX_HOLD 모두 재진입 차단)
            date_key = datetime.now().strftime('%Y-%m-%d')
            daily = pos_data.get('daily_counts', {})
            if daily.get('date') != date_key:
                daily = {'date': date_key}
            closed_today = daily.get('closed_tickers', [])
            if ticker not in closed_today:
                closed_today.append(ticker)
            daily['closed_tickers'] = closed_today
            pos_data['daily_counts'] = daily
            # 즉시 반영 (check_positions → open_positions 순서 보장)
            pos_data.setdefault('_closed_today_runtime', set()).add(ticker)

            # 타임프레임별 쿨다운 기록 (4H=4시간, daily=24시간 재진입 차단)
            tf_closed = pos.get('timeframe', '15m')
            cooldown_min = {'4H': 240, 'daily': 1440}.get(tf_closed, 0)
            if cooldown_min > 0:
                cooldown_until = (datetime.now() + timedelta(minutes=cooldown_min)).strftime('%Y-%m-%d %H:%M:%S')
                cooldowns = pos_data.setdefault('tf_cooldowns', {})
                cooldowns[ticker] = {'until': cooldown_until, 'tf': tf_closed}

            result_icon = 'WIN' if win else 'LOSS'
            print(f"    [{result_icon}] {pos.get('name', ticker)} | "
                  f"{reason} | 진입={entry:.4f} 청산={exit_price:.4f} | "
                  f"PnL={pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)")
        else:
            remaining.append(pos)

    pos_data['positions'] = remaining
    return closed


# ── 신규 포지션 진입 ─────────────────────────────────────────────
def open_positions(signals: list, pos_data: dict, portfolio: dict):
    """tradeable 신호로 신규 가상 포지션 생성"""
    now_str  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_key = datetime.now().strftime('%Y-%m-%d')

    # 현재 오픈 포지션 — 티커별 마지막 진입 시각 추적 (중복 허용, 쿨다운만 적용)
    open_ticker_times: dict = {}
    for p in pos_data.get('positions', []):
        tk = p['ticker']
        ot = p.get('open_time', '')
        if tk not in open_ticker_times or ot > open_ticker_times[tk]:
            open_ticker_times[tk] = ot

    # 일일 카운트 (날짜 바뀌면 리셋)
    daily = pos_data.get('daily_counts', {})
    if daily.get('date') != date_key:
        daily = {'date': date_key}
    pos_data['daily_counts'] = daily

    # 당일 장 중 SL 청산된 티커만 재진입 차단 (장 외 시간 SL은 제외)
    # KR: 09~17시, US: 22~06시, CRYPTO: 전 시간
    MARKET_HOURS_BLOCK = {
        'KR':     set(range(9, 17)),
        'US':     set(range(22, 24)) | set(range(0, 7)),
        'CRYPTO': set(range(0, 24)),
    }
    closed_today: set = set(daily.get('closed_tickers', [])) | pos_data.get('_closed_today_runtime', set())
    try:
        import csv as _csv
        if TRADES_FILE.exists():
            with open(TRADES_FILE, encoding='utf-8-sig') as _f:
                for _row in _csv.DictReader(_f):
                    if not _row.get('close_time', '').startswith(date_key):
                        continue
                    # 장 외 시간 SL은 차단 목록에서 제외
                    mkt = _row.get('market', 'CRYPTO')
                    try:
                        close_hour = int(_row['close_time'][11:13])
                    except Exception:
                        close_hour = -1
                    allowed_hours = MARKET_HOURS_BLOCK.get(mkt, set(range(0, 24)))
                    if close_hour not in allowed_hours and _row.get('close_reason') == 'SL':
                        continue  # 장 외 SL → 재진입 허용
                    closed_today.add(_row['ticker'])
    except Exception:
        pass

    # 현재 오픈 중인 ticker+timeframe 집합 (완전 중복 차단용)
    open_ticker_tf: set = {
        (p['ticker'], p.get('timeframe', '15m'))
        for p in pos_data.get('positions', [])
    }

    for sig in signals:
        if not sig.get('tradeable', True):
            continue

        ticker = sig['ticker']
        market = sig.get('market', 'CRYPTO')

        # 화이트리스트 검증 — 어떤 경로로 들어오든 유니버스 외 종목 영구 차단
        allowed = _HARD_WL.get(market, set())
        if allowed and ticker not in allowed:
            print(f"    [하드차단] {sig.get('name', ticker)}({ticker}) {market} — 유니버스 외 종목")
            continue

        # quality_score 최소 4점 이상만 진입 (이중 방어선)
        if sig.get('quality_score', 0) < 4:
            print(f"    [품질차단] {sig.get('name', ticker)} Q={sig.get('quality_score', 0)}/7 — 4점 미달")
            continue

        # 동일 ticker + timeframe 완전 중복 차단 — 이미 오픈 포지션 있으면 진입 불가
        tf_sig = sig.get('timeframe', '15m')
        if (ticker, tf_sig) in open_ticker_tf:
            print(f"    [중복차단] {sig.get('name', ticker)} {tf_sig} — 동일 포지션 이미 오픈 중")
            continue

        # 동일 종목 쿨다운 체크 (완전 차단 아님 — 조건 충족시 추가 진입 허용)
        if ticker in open_ticker_times:
            try:
                last_entry = datetime.fromisoformat(open_ticker_times[ticker])
                elapsed_min = (datetime.now() - last_entry).total_seconds() / 60
                # 타임프레임별 최소 재진입 간격
                min_gap = {'daily': 240, '4H': 120, '1H': 60}.get(tf_sig, 30)
                if elapsed_min < min_gap:
                    continue   # 쿨다운 미경과 → 스킵
            except Exception:
                pass

        # 당일 청산 종목 재진입 차단 (전 타임프레임 — 4H/daily 포함)
        if ticker in closed_today:
            continue

        # ── 스캔 vs 진입 분리 (v4.5) ──────────────────────────────
        # KR/US 15m: 보조지표 3종 필터로 활용 (2개 이상 충족 시 진입)
        # CRYPTO 15m: 수수료 0.1% → 진입 허용
        # KR/US 4H/daily: 진입 허용
        if market in ('KR', 'US') and tf_sig == '15m':
            # 15m 보조 필터 3종 (2026-04-29 확정): EMA정렬 + CHoCH + SL정밀화
            tags = sig.get('quality_tags', '')
            ema_ok   = 'EMA_Align' in tags                    # ① EMA 정배열
            choch_ok = 'CHoCH' in tags                        # ② 구조전환(CHoCH)
            sl_ok    = sig.get('sl_pct', -999) >= -1.5        # ③ SL 정밀화 (-1.5% 이내)
            score_15m = sum([ema_ok, choch_ok, sl_ok])

            if score_15m >= 2:
                print(f"    [15m보조✅] {sig.get('name', ticker)} {market}/15m | "
                      f"EMA={ema_ok} CHoCH={choch_ok} SL={sl_ok} → 진입 허용")
            else:
                print(f"    [15m보조❌] {sig.get('name', ticker)} {market}/15m | "
                      f"EMA={ema_ok} CHoCH={choch_ok} SL={sl_ok} ({score_15m}/3) → 필터 미달")
                continue
        # 4H/daily: 쿨다운 시간 내 재진입 차단 (4H=4시간, daily=24시간)
        cooldowns = pos_data.get('tf_cooldowns', {})
        if ticker in cooldowns:
            until_str = cooldowns[ticker].get('until', '')
            try:
                until_dt = datetime.fromisoformat(until_str)
                if datetime.now() < until_dt:
                    remaining_min = int((until_dt - datetime.now()).total_seconds() / 60)
                    print(f"    [쿨다운] {sig.get('name', ticker)} {tf_sig} — {remaining_min}분 후 재진입 가능")
                    continue
            except Exception:
                pass

        # V5.0 섹터 집중도 체크 (동일 섹터 최대 2포지션 — CRYPTO 제외)
        if market != 'CRYPTO':
            sector = SECTOR_MAP.get(ticker, ticker)
            sector_count = sum(
                1 for p in pos_data['positions']
                if SECTOR_MAP.get(p['ticker'], p['ticker']) == sector
            )
            if sector_count >= MAX_SECTOR_POSITIONS:
                print(f"    [섹터차단] {sig.get('name', ticker)} — {sector} 섹터 {sector_count}개 한도({MAX_SECTOR_POSITIONS}개) 초과")
                continue

        # 시장별 포지션 수 체크
        mkt_positions = [p for p in pos_data['positions'] if p['market'] == market]
        if len(mkt_positions) >= MAX_POS_PER_MARKET.get(market, 5):
            continue

        # 일중 거래 건수 제한: 시장별 하루 최대 3건 (품질 선별)
        MAX_DAILY_TRADES = {'KR': 10, 'US': 10, 'CRYPTO': 10}  # 일중 최대 10건
        today_str = datetime.now().strftime('%Y-%m-%d')
        daily_key = f"{market}_{today_str}"
        daily_trade_count = pos_data.get('daily_counts', {}).get(daily_key, 0)
        if daily_trade_count >= MAX_DAILY_TRADES.get(market, 3):
            print(f"    [일중한도] {market} 오늘 {daily_trade_count}건 완료 — 추가 진입 차단")
            continue

        # 자본 여유 확인
        avail = portfolio['capital'].get(market, 0)
        pos_size = POSITION_SIZE.get(market, 5_000_000)
        if avail < pos_size:
            print(f"    [{market}] 자금 부족 — {avail:,.0f}원 (필요: {pos_size:,.0f}원)")
            continue

        # 포지션 생성
        portfolio['capital'][market] = avail - pos_size
        tf = sig.get('timeframe', '15m')

        tags = sig.get('quality_tags', '')
        pos = {
            'open_time':       now_str,
            'ticker':          ticker,
            'name':            sig.get('name', ticker),
            'market':          market,
            'timeframe':       tf,
            'signal_type':     sig.get('type', ''),
            'entry':           sig['entry'],
            'sl':              sig['sl'],
            'tp':              sig['tp'],
            'sl_pct':          sig.get('sl_pct', 0),
            'tp_pct':          sig.get('tp_pct', 0),
            'size_krw':        pos_size,
            'quality_score':   sig.get('quality_score', 0),
            'quality_tags':    tags,
            'entry_hour_kst':  (datetime.now().hour + 9) % 24,
            'vol_ratio':       sig.get('vol_ratio', 0),
            'has_vol_spike':   'Vol_Spike'    in tags,
            'has_liq_sweep':   'Liq_Sweep'   in tags,
            'has_choch':       'CHoCH'        in tags,
            'has_body_in_zone':'Body_In_Zone' in tags,
            'has_pinbar':      'PinBar'       in tags,
            'has_ema_align':   'EMA_Align'    in tags,
            'has_fresh_zone':  'Fresh_Zone'   in tags,
        }
        pos_data['positions'].append(pos)
        open_ticker_times[ticker] = now_str  # 마지막 진입 시각 업데이트
        open_ticker_tf.add((ticker, tf_sig))  # 중복 차단 집합 업데이트
        # 일중 거래 카운터 증가
        dc = pos_data.setdefault('daily_counts', {})
        dc[daily_key] = dc.get(daily_key, 0) + 1

        # V5.2 ATR 기반 권장 포지션 계산 (로그 참고용 — 실제 주문은 pos_size 고정)
        total_equity = sum(portfolio.get('capital', {}).values()) + sum(
            p.get('size_krw', 0) for p in pos_data.get('positions', []))
        atr_pct = _get_atr(ticker, market=market)   # ATR% (없으면 None)
        sizing  = calc_risk_based_position_size(
            total_equity     = total_equity,
            entry_price      = sig['entry'],
            sl_price         = sig['sl'],
            max_position_krw = POSITION_SIZE.get(market, 5_000_000) * 3,
            atr_pct          = atr_pct,
        )
        # 비교 로그: 고정 vs SL기반 vs ATR기반
        atr_log = (f"ATR={sizing['atr_pct_used']:.2f}%→{sizing['atr_based_krw']:,.0f}원"
                   if atr_pct else "ATR=N/A")
        print(f"    [진입] {sig.get('name', ticker)} [{tf}] | {sig.get('type','')} | "
              f"진입={sig['entry']:.4f} | TP=+{sig.get('tp_pct',0):.2f}% | "
              f"SL={sig.get('sl_pct',0):.2f}% | Q={sig.get('quality_score',0)}/7")
        print(f"    [사이즈] 고정={pos_size:,.0f} | "
              f"SL기반={sizing['sl_based_krw']:,.0f} | {atr_log} | "
              f"리스크허용={sizing['risk_krw']:,.0f}원")


# ── 상태 출력 ────────────────────────────────────────────────────
def print_status():
    pos_data  = _load_positions()
    portfolio = _load_portfolio()

    total_init = sum(INITIAL_CAPITAL.values())
    total_now  = sum(portfolio['capital'].values())
    total_pnl  = sum(portfolio['realized_pnl'].values())
    total_tr   = portfolio.get('total_trades', 0)
    wins       = portfolio.get('wins', 0)
    wr         = wins / total_tr * 100 if total_tr > 0 else 0
    start_date = portfolio.get('start_date', '?')
    try:
        fmt = '%Y-%m-%d %H:%M:%S' if len(start_date) > 10 else '%Y-%m-%d'
        days = (datetime.now() - datetime.strptime(start_date, fmt)).days
    except Exception:
        days = 0

    print(f"\n{'='*65}")
    print(f"  Warren Paper Trading 현황 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    print(f"  운영 기간: {start_date} ~ 오늘 ({days}일째)")
    print(f"{'='*65}")
    print(f"\n  [포트폴리오]")
    print(f"  초기자금:  {total_init:>14,.0f}원")
    print(f"  현재자금:  {total_now:>14,.0f}원  ({(total_now-total_init)/total_init*100:+.2f}%)")
    print(f"  실현손익:  {total_pnl:>14,.0f}원")

    print(f"\n  [시장별 현황]")
    for mkt in ['KR', 'US', 'CRYPTO']:
        init   = INITIAL_CAPITAL.get(mkt, 0)
        now    = portfolio['capital'].get(mkt, 0)
        pnl    = portfolio['realized_pnl'].get(mkt, 0)
        n_pos  = len([p for p in pos_data['positions'] if p['market'] == mkt])
        print(f"  {mkt:<8} 자금={now:>10,.0f}원  실현={pnl:>+10,.0f}원  포지션={n_pos}개")

    print(f"\n  [거래 성과]")
    print(f"  총거래:  {total_tr}건  |  승률: {wr:.1f}%  ({wins}승 {total_tr-wins}패)")

    if pos_data['positions']:
        print(f"\n  [오픈 포지션 {len(pos_data['positions'])}개]")
        for p in pos_data['positions']:
            cur = _get_price(p['ticker'], market=p.get('market', ''))
            if cur:
                pnl_pct = (cur - p['entry']) / p['entry'] * 100
                print(f"  {p.get('name', p['ticker']):<12} [{p['timeframe']}] | "
                      f"진입={p['entry']:.4f} | 현재={cur:.4f} | "
                      f"미실현={pnl_pct:+.2f}%")
            else:
                print(f"  {p.get('name', p['ticker']):<12} [{p['timeframe']}] | "
                      f"진입={p['entry']:.4f} | 가격조회실패")
    else:
        print(f"\n  오픈 포지션 없음")
    print(f"{'='*65}\n")


# ── 메인 1회 실행 ────────────────────────────────────────────────
def run_once():
    # ── 중복 실행 방지 ──────────────────────────────────────────
    if not _acquire_lock():
        return   # 다른 프로세스가 실행 중이면 즉시 종료

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*65}")
    print(f"  Warren Bot v5.3 [{now_str}]")
    print(f"  KR16 + US10 + CRYPTO4 | CB-1.5%/Week-5%/MDD-10% | ATR Sizing")
    print(f"{'='*65}")

    pos_data  = _load_positions()
    portfolio = _load_portfolio()

    # 1) 오픈 포지션 SL/TP 체크
    print(f"\n  [1] 포지션 점검 ({len(pos_data['positions'])}개 오픈)")
    closed = check_positions(pos_data, portfolio)
    if not closed:
        print(f"    청산 없음")

    # 2) 신호 스캔 (필터링 포함)
    print(f"\n  [2] 신호 스캔 (FVG+OB★ 품질4점↑ + 하루5건 + 고유동성시간)")
    signals = scan_all()
    tradeable = [s for s in signals if s.get('tradeable', True)]
    print(f"    tradeable 신호: {len(tradeable)}건")

    # 3) 신규 포지션 진입 (서킷브레이커 선행 체크)
    print(f"\n  [3] 신규 진입 검토")
    halted, cb_reason = _check_circuit_breaker(portfolio, pos_data)
    if halted:
        print(f"  {cb_reason}")
        print(f"    신규 진입 전면 차단")
    elif tradeable:
        open_positions(tradeable, pos_data, portfolio)
    else:
        print(f"    진입 신호 없음")

    # 4) 저장
    _save_positions(pos_data)
    _save_portfolio(portfolio)

    # 5) 성과 분석 리포트 (V5.3)
    perf = _compute_performance_report()
    w_all = perf['windows'].get('all', {})
    w_30  = perf['windows'].get('30d', {})

    # 6) 현황 요약
    total_tr = portfolio.get('total_trades', 0)
    wins     = portfolio.get('wins', 0)
    wr       = wins / total_tr * 100 if total_tr > 0 else 0
    total_pnl = sum(portfolio['realized_pnl'].values())
    print(f"\n  [요약] 누적거래={total_tr}건 | 승률={wr:.1f}% | "
          f"실현손익={total_pnl:+,.0f}원 | 오픈={len(pos_data['positions'])}개")

    # 성과 리포트 요약 출력
    if w_all.get('trades', 0) > 0:
        print(f"  [성과-전체] PF={w_all['profit_factor']} | "
              f"Exp={w_all['expectancy_krw']:+,.0f}원 | "
              f"Sharpe={w_all['sharpe']} | "
              f"MDD={w_all['max_drawdown_pct']:.1f}%")
    if w_30.get('trades', 0) > 0:
        print(f"  [성과-30d] 거래={w_30['trades']}건 | "
              f"WR={w_30['win_rate']}% | "
              f"PF={w_30['profit_factor']} | "
              f"Exp={w_30['expectancy_krw']:+,.0f}원")
    print(f"{'='*65}\n")


# ── 루프 실행 (15분마다) ─────────────────────────────────────────
def run_loop(interval_min: int = 15):
    print(f"  Paper Trading 루프 시작 — {interval_min}분마다 실행")
    print(f"  종료: Ctrl+C\n")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"  [오류] {e}")
        next_run = datetime.now() + timedelta(minutes=interval_min)
        print(f"  다음 실행: {next_run.strftime('%H:%M:%S')} (약 {interval_min}분 후)")
        time.sleep(interval_min * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop',   action='store_true', help='15분마다 자동 반복')
    parser.add_argument('--status', action='store_true', help='현재 상태 출력')
    parser.add_argument('--interval', type=int, default=15, help='루프 간격(분)')
    args = parser.parse_args()

    if args.status:
        print_status()
    elif args.loop:
        run_loop(args.interval)
    else:
        run_once()
