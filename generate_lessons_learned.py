# -*- coding: utf-8 -*-
"""
Lessons Learned 자동 생성 스크립트 — 매일 21:00 실행
오늘의 거래 복기, 전략 변경사항, 내일 주목 종목을 JSON으로 저장
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR   = Path(__file__).parent
LOG_DIR    = BASE_DIR / 'logs'
LL_FILE    = LOG_DIR / 'lessons_learned.json'
PORT_FILE  = LOG_DIR / 'paper_portfolio.json'
POS_FILE   = LOG_DIR / 'paper_positions.json'
TRADE_FILE = LOG_DIR / 'paper_trades.csv'

today_str = datetime.now().strftime('%Y-%m-%d')


def load_portfolio() -> dict:
    if not PORT_FILE.exists():
        return {}
    return json.loads(PORT_FILE.read_text(encoding='utf-8'))


def load_positions() -> list:
    if not POS_FILE.exists():
        return []
    data = json.loads(POS_FILE.read_text(encoding='utf-8'))
    return data.get('positions', [])


def load_today_trades() -> list:
    if not TRADE_FILE.exists():
        return []
    import csv
    trades = []
    with open(TRADE_FILE, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('close_time', '').startswith(today_str):
                trades.append(row)
    return trades


def calc_portfolio_summary(portfolio: dict, positions: list, today_trades: list) -> dict:
    capital  = portfolio.get('capital', {})
    initial  = portfolio.get('initial_capital', {})
    real_pnl = portfolio.get('realized_pnl', {})

    invested = {'KR': 0, 'US': 0, 'CRYPTO': 0}
    for p in positions:
        mkt = p.get('market', 'KR')
        if mkt in invested:
            invested[mkt] += p.get('size_krw', 0)

    total_assets = sum(capital.get(m, 0) + invested.get(m, 0) for m in ('KR', 'US', 'CRYPTO'))
    total_initial = sum(initial.get(m, 0) for m in ('KR', 'US', 'CRYPTO'))
    total_realized = sum(real_pnl.get(m, 0) for m in ('KR', 'US', 'CRYPTO'))
    daily_pnl = sum(float(t.get('pnl_krw', 0)) for t in today_trades)

    return {
        'total_assets':  total_assets,
        'total_initial': total_initial,
        'realized_pnl':  total_realized,
        'daily_pnl':     daily_pnl,
        'open_positions': len(positions),
        'today_trades':  len(today_trades),
        'today_wins':    sum(1 for t in today_trades if t.get('result') == 'WIN'),
        'today_losses':  sum(1 for t in today_trades if t.get('result') == 'LOSS'),
    }


def build_lessons(today_trades: list, positions: list) -> list:
    """오늘 거래 기반 자동 교훈 도출"""
    lessons = []

    losses = [t for t in today_trades if t.get('result') == 'LOSS']
    wins   = [t for t in today_trades if t.get('result') == 'WIN']

    # 손실 분석
    if losses:
        loss_names = ', '.join(t.get('name', t.get('ticker','')) for t in losses)
        lessons.append({
            'category': '리스크',
            'content': f"오늘 손실 {len(losses)}건: {loss_names}",
            'action': '15m 필터(EMA정렬+CHoCH) 차단 여부 확인 필요'
        })

    # 승률 평가
    total = len(today_trades)
    if total > 0:
        wr = len(wins) / total * 100
        if wr >= 70:
            lessons.append({
                'category': '성과',
                'content': f"오늘 승률 {wr:.0f}% — 전략 유효",
                'action': '현 전략 유지'
            })
        elif wr < 50 and total >= 3:
            lessons.append({
                'category': '경고',
                'content': f"오늘 승률 {wr:.0f}% — 전략 점검 필요",
                'action': '진입 조건 강화 또는 시장 국면 재확인'
            })

    # 오픈 포지션 점검
    if len(positions) >= 4:
        lessons.append({
            'category': '포지션 관리',
            'content': f"현재 {len(positions)}개 포지션 동시 운용 중",
            'action': '추가 진입 신중히 — 리스크 분산 확인'
        })

    # 거래 없을 때
    if total == 0:
        lessons.append({
            'category': '시장 관찰',
            'content': '오늘 청산된 거래 없음 — 오픈 포지션 유지 또는 시그널 부재',
            'action': '내일 시장 오픈 시 스캔 결과 재확인'
        })

    return lessons


def build_strategy_changes() -> list:
    """오늘 적용된 전략 변경사항 (날짜 기반 고정 기록)"""
    # 2026-04-29 변경사항 하드코딩 (이후 날짜는 동적으로 추가)
    today = datetime.now().strftime('%Y-%m-%d')
    if today == '2026-04-29':
        return [
            "자본 재배분: KR 5,000만 / US 1억 / CRYPTO 5,000만 (총 2억)",
            "15m 보조 필터 3종 적용: EMA정렬 + CHoCH + SL정밀화",
            "종목 유니버스 확대: KR 8→13종목, US 5→10종목",
            "포지션 사이즈: 10%→20% (최대 5개 동시)",
            "일중 거래 한도: 시장별 최대 10건",
            "월 현실 목표: 1,000만원 (복리 재투자로 시드 확대)",
        ]
    return []


def build_watchlist(positions: list) -> list:
    """내일 주목할 오픈 포지션 목록"""
    watchlist = []
    for p in positions:
        tp  = p.get('tp', 0)
        sl  = p.get('sl', 0)
        entry = p.get('entry', 0)
        if entry > 0:
            tp_pct = (tp - entry) / entry * 100
            sl_pct = (sl - entry) / entry * 100
            watchlist.append({
                '종목': p.get('name', p.get('ticker','')),
                '시장': p.get('market',''),
                '진입가': f"{entry:,.2f}",
                'TP': f"{tp:,.2f} ({tp_pct:+.1f}%)",
                'SL': f"{sl:,.2f} ({sl_pct:+.1f}%)",
                '상태': '모니터링'
            })
    return watchlist


def main():
    print(f"=== Lessons Learned 생성 ({today_str} 21:00) ===")

    portfolio    = load_portfolio()
    positions    = load_positions()
    today_trades = load_today_trades()

    port_summary = calc_portfolio_summary(portfolio, positions, today_trades)
    lessons      = build_lessons(today_trades, positions)
    changes      = build_strategy_changes()
    watchlist    = build_watchlist(positions)

    new_entry = {
        'date':              today_str,
        'generated_at':      datetime.now().strftime('%Y-%m-%d %H:%M'),
        'portfolio_summary': port_summary,
        'lessons':           lessons,
        'strategy_changes':  changes,
        'tomorrow_watchlist': watchlist,
    }

    # 기존 파일에 append (날짜별 누적)
    if LL_FILE.exists():
        existing = json.loads(LL_FILE.read_text(encoding='utf-8'))
        if not isinstance(existing, list):
            existing = [existing]
        # 같은 날짜면 덮어쓰기
        existing = [e for e in existing if e.get('date') != today_str]
        existing.append(new_entry)
    else:
        existing = [new_entry]

    LL_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"저장 완료: {LL_FILE}")
    print(f"총 자산: {port_summary['total_assets']//10000:,}만원")
    print(f"당일 손익: {port_summary['daily_pnl']//10000:+,}만원")
    print(f"교훈 {len(lessons)}건 / 전략 변경 {len(changes)}건 / 주목 종목 {len(watchlist)}건")


if __name__ == '__main__':
    main()
