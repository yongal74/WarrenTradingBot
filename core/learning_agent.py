# -*- coding: utf-8 -*-
"""
Warren 매일 복기 학습 에이전트
15:35 자동 실행 (Windows Task Scheduler)

1. 오늘 데이터로 25개 전략 전부 시뮬레이션
2. "이 전략 썼으면 얼마였나?" 비교
3. 14일 롤링 성과로 최적 전략 선정
4. 텔레그램으로 학습 리포트 발송
5. 성과 좋은 전략 자동 우선순위 조정
"""
import warnings; warnings.filterwarnings('ignore')
import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from config.assets import ALL_ASSETS
from data.data_loader import load
from core.strategy_factory import _compute_all, _atr

# ── 경로 ─────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent.parent
LOG_DIR          = BASE_DIR / 'logs'
PRIORITY_FILE    = BASE_DIR / 'config' / 'strategy_priorities.json'
LEARNING_LOG     = LOG_DIR / 'learning_log.csv'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 시뮬 파라미터 ─────────────────────────────────────────
ROLLING_DAYS     = 14    # 14일 롤링 성과
HOLD_BARS        = 5     # 신호 진입 후 최대 보유 봉수 (일봉 기준)
MIN_TRADES       = 3     # 최소 거래수 (랭킹 포함 조건)

# ── 텔레그램 ──────────────────────────────────────────────
_TG_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
_TG_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')


def _tg(msg: str):
    if not _TG_TOKEN or not _TG_CHAT_ID:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{_TG_TOKEN}/sendMessage',
            json={'chat_id': _TG_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'},
            timeout=10,
        )
    except Exception:
        pass


# ── 전략 시뮬레이션 ───────────────────────────────────────
def _simulate_strategy(df: pd.DataFrame, signals: pd.Series,
                        hold_bars: int = HOLD_BARS) -> list:
    """
    신호 시리즈로 단순 P&L 시뮬:
    신호 0→1 전환 = 다음 봉 Open 진입
    신호 1→0 전환 or HOLD_BARS 경과 = 다음 봉 Open 청산
    Returns: list of {'entry_date', 'exit_date', 'pnl_pct', 'win'}
    """
    trades = []
    in_pos = False
    entry_price = 0.0
    entry_bar = 0

    for i in range(1, len(df)):
        sig_prev = int(signals.iloc[i - 1]) if not pd.isna(signals.iloc[i - 1]) else 0
        sig_cur  = int(signals.iloc[i])     if not pd.isna(signals.iloc[i])      else 0

        if not in_pos and sig_prev == 0 and sig_cur == 1:
            # 진입: 현재봉 Open
            entry_price = float(df['Open'].iloc[i])
            entry_bar   = i
            in_pos      = True

        elif in_pos:
            # 청산 조건: 신호 소멸 or 최대 보유 봉수
            if sig_cur == 0 or (i - entry_bar) >= hold_bars:
                exit_price = float(df['Open'].iloc[i])
                pnl_pct = (exit_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
                trades.append({
                    'entry_date': str(df.index[entry_bar])[:10],
                    'exit_date':  str(df.index[i])[:10],
                    'pnl_pct':    round(pnl_pct, 3),
                    'win':        pnl_pct > 0,
                })
                in_pos = False
                entry_price = 0.0

    return trades


def _rolling_stats(trades: list, days: int = ROLLING_DAYS) -> dict:
    """최근 N일 거래만 필터해서 성과 통계 계산"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    recent = [t for t in trades if t['entry_date'] >= cutoff]

    if len(recent) < MIN_TRADES:
        return {'n': len(recent), 'win_rate': 0.0, 'total_pnl': 0.0,
                'avg_pnl': 0.0, 'sharpe': 0.0}

    pnls = [t['pnl_pct'] for t in recent]
    wins = [t for t in recent if t['win']]
    win_rate   = len(wins) / len(recent) * 100
    total_pnl  = sum(pnls)
    avg_pnl    = total_pnl / len(recent)
    std_pnl    = float(np.std(pnls)) if len(pnls) > 1 else 1.0
    sharpe     = avg_pnl / std_pnl if std_pnl > 0 else 0.0

    return {
        'n':         len(recent),
        'win_rate':  round(win_rate, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl':   round(avg_pnl, 3),
        'sharpe':    round(sharpe, 3),
    }


# ── 전략 우선순위 파일 I/O ────────────────────────────────
def _load_priorities() -> dict:
    if PRIORITY_FILE.exists():
        with open(PRIORITY_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_priorities(priorities: dict):
    PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRIORITY_FILE, 'w', encoding='utf-8') as f:
        json.dump(priorities, f, ensure_ascii=False, indent=2)


def get_best_strategy(ticker: str, default: str = 'S17_FVG') -> str:
    """대시보드/포워드테스터에서 사용: 종목별 현재 1순위 전략 반환"""
    p = _load_priorities()
    return p.get(ticker, {}).get('best_strategy', default)


# ── 메인 학습 루프 ────────────────────────────────────────
def run_learning() -> dict:
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today   = date.today().strftime('%Y-%m-%d')

    print(f"\n{'='*65}")
    print(f"  Warren 학습 에이전트 [{now_str}]")
    print(f"  14일 롤링 성과 기반 전략 우선순위 자동 조정")
    print(f"{'='*65}\n")

    priorities = _load_priorities()
    report_lines: list[str] = []
    log_rows: list[dict] = []
    changed_tickers: list[str] = []

    for ticker, asset in ALL_ASSETS.items():
        market = asset['market']
        name   = asset['name']

        df = load(ticker, market)
        if df is None or len(df) < 80:
            print(f"  [{ticker}] 데이터 부족 — 건너뜀")
            continue

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # 모든 25개 전략 신호 계산
        all_signals = _compute_all(df)

        # 전략별 시뮬 + 롤링 성과
        strategy_stats: dict[str, dict] = {}
        for strat_name, sig_series in all_signals.items():
            trades = _simulate_strategy(df, sig_series)
            stats  = _rolling_stats(trades)
            strategy_stats[strat_name] = stats

        # 유효한 전략만 (최소 MIN_TRADES 이상)
        valid = {k: v for k, v in strategy_stats.items() if v['n'] >= MIN_TRADES}

        if not valid:
            print(f"  [{ticker}] {name}: 유효 전략 없음 (거래수 부족)")
            continue

        # 샤프 > 0 우선, 그 다음 win_rate 기준 정렬
        ranked = sorted(valid.items(),
                        key=lambda x: (x[1]['sharpe'], x[1]['win_rate']),
                        reverse=True)
        best_strat = ranked[0][0]
        best_stats = ranked[0][1]

        # 이전 우선순위와 비교
        prev_best = priorities.get(ticker, {}).get('best_strategy', '')
        if prev_best != best_strat:
            changed_tickers.append(f"{ticker}({name}): {prev_best} → {best_strat}")

        # 우선순위 업데이트
        priorities[ticker] = {
            'best_strategy': best_strat,
            'updated_at':    today,
            'stats_14d':     best_stats,
            'top3': [
                {'strategy': k, **v}
                for k, v in ranked[:3]
            ],
        }

        # 로그 행
        log_rows.append({
            'date':          today,
            'ticker':        ticker,
            'name':          name,
            'market':        market,
            'best_strategy': best_strat,
            'win_rate_14d':  best_stats['win_rate'],
            'total_pnl_14d': best_stats['total_pnl'],
            'sharpe_14d':    best_stats['sharpe'],
            'trades_14d':    best_stats['n'],
        })

        tier = '★★' if best_stats['win_rate'] >= 55 else ('★' if best_stats['win_rate'] >= 45 else '·')
        print(f"  [{ticker}] {name:<12} | {best_strat:<18} | "
              f"승률={best_stats['win_rate']:.0f}% Sharpe={best_stats['sharpe']:.2f} "
              f"PnL={best_stats['total_pnl']:+.2f}% N={best_stats['n']} {tier}")

        report_lines.append(
            f"{tier} <b>{name}({ticker})</b> [{market}]\n"
            f"   전략: {best_strat} | 승률: {best_stats['win_rate']:.0f}% "
            f"| Sharpe: {best_stats['sharpe']:.2f} | 14일PnL: {best_stats['total_pnl']:+.2f}%"
        )

    # 우선순위 파일 저장
    _save_priorities(priorities)
    print(f"\n  [우선순위] {PRIORITY_FILE} 저장 완료")

    # 학습 로그 CSV 누적
    if log_rows:
        df_log = pd.DataFrame(log_rows)
        if LEARNING_LOG.exists():
            df_log.to_csv(LEARNING_LOG, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df_log.to_csv(LEARNING_LOG, index=False, encoding='utf-8-sig')
        print(f"  [학습로그] {len(log_rows)}개 종목 기록")

    # 텔레그램 리포트 발송
    _send_report(report_lines, changed_tickers, today)

    return {'updated': len(log_rows), 'changed': changed_tickers}


def _send_report(lines: list, changed: list, today: str):
    if not lines:
        return

    header = (
        f"<b>[Warren] 매일 복기 학습 리포트</b>\n"
        f"{today} 15:35 자동 분석\n"
        f"14일 롤링 성과 기반 전략 우선순위 갱신\n"
        f"{'─' * 30}\n"
    )

    # 최대 4096자 (텔레그램 한도)
    body = "\n\n".join(lines[:14])  # 14종목

    footer_parts = [f"\n{'─' * 30}"]
    if changed:
        footer_parts.append(f"<b>전략 변경 ({len(changed)}건):</b>")
        footer_parts.extend(changed)
    else:
        footer_parts.append("전략 변경 없음 — 현행 유지")
    footer_parts.append("\n★★=승률55%+ ★=45%+ ·=45%미만")
    footer = "\n".join(footer_parts)

    msg = header + body + footer
    if len(msg) > 4000:
        msg = msg[:4000] + "\n...(생략)"

    _tg(msg)
    print(f"  [Telegram] 학습 리포트 발송 완료")


if __name__ == '__main__':
    result = run_learning()
    print(f"\n  완료: {result['updated']}종목 분석, 전략 변경 {len(result['changed'])}건")
