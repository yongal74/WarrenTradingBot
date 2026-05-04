# -*- coding: utf-8 -*-
"""
compare_versions.py — V1 / V2 / V3 성과 비교
=============================================
실행: python compare_versions.py
"""
import sys, csv, json
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LOGS = Path(__file__).parent / 'logs'
VERSIONS = ['v1', 'v2', 'v3']
VERSION_NAMES = {
    'v1': 'V1 FVG+OB (버그수정)',
    'v2': 'V2 FVG+DBB (클린)',
    'v3': 'V3 EMA눌림목 (신규)',
}


def _load_trades(version: str) -> list:
    f = LOGS / f'{version}_trades.csv'
    if not f.exists():
        return []
    with open(f, newline='', encoding='utf-8-sig') as fp:
        return list(csv.DictReader(fp))


def _load_portfolio(version: str) -> dict:
    f = LOGS / f'{version}_portfolio.json'
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text('utf-8'))
    except Exception:
        return {}


def _calc_stats(trades: list) -> dict:
    if not trades:
        return {'trades': 0}

    wins   = [t for t in trades if t.get('result') == 'WIN']
    losses = [t for t in trades if t.get('result') == 'LOSS']
    pnls   = [float(t.get('pnl_krw', 0)) for t in trades]

    total    = len(trades)
    wr       = len(wins) / total * 100 if total else 0
    avg_win  = sum(float(t['pnl_krw']) for t in wins)  / len(wins)  if wins   else 0
    avg_loss = sum(float(t['pnl_krw']) for t in losses) / len(losses) if losses else 0
    gross_p  = sum(float(t['pnl_krw']) for t in wins)
    gross_l  = abs(sum(float(t['pnl_krw']) for t in losses))
    pf       = gross_p / gross_l if gross_l > 0 else float('inf')
    exp      = sum(pnls) / total if total else 0

    # 최대 연속 손실
    streak = max_streak = 0
    for t in trades:
        if t.get('result') == 'LOSS':
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        'trades':     total,
        'wins':       len(wins),
        'losses':     len(losses),
        'win_rate':   round(wr, 1),
        'avg_win':    round(avg_win),
        'avg_loss':   round(avg_loss),
        'pf':         round(pf, 2) if pf != float('inf') else '∞',
        'expectancy': round(exp),
        'total_pnl':  round(sum(pnls)),
        'max_streak': max_streak,
    }


def _capital_summary(pf: dict) -> dict:
    if not pf:
        return {}
    initial = pf.get('initial', {})
    capital = pf.get('capital', {})
    t_init  = sum(initial.values())
    t_now   = sum(capital.values())
    ret     = (t_now - t_init) / t_init * 100 if t_init else 0
    return {
        'total_init': t_init,
        'total_now':  t_now,
        'return_pct': round(ret, 2),
        'start':      pf.get('start', '-'),
    }


def print_comparison():
    sep = '─' * 80
    print('\n' + '=' * 80)
    print('  Warren Paper Trading — 버전별 성과 비교')
    print(f'  생성시각: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 80)

    all_stats = {}
    for v in VERSIONS:
        trades  = _load_trades(v)
        pf      = _load_portfolio(v)
        stats   = _calc_stats(trades)
        capital = _capital_summary(pf)
        all_stats[v] = {'stats': stats, 'capital': capital}

    # 자본 현황
    print(f'\n  {"버전":<22} {"시작일":<16} {"초기자본":>10} {"현재자산":>10} {"수익률":>8}')
    print(f'  {sep[:70]}')
    for v in VERSIONS:
        c = all_stats[v]['capital']
        if not c:
            print(f'  {VERSION_NAMES[v]:<22}  {"(데이터없음)"}')
            continue
        ret_str = f"{c['return_pct']:+.1f}%"
        print(f'  {VERSION_NAMES[v]:<22}  {c["start"]:<16}'
              f'  {c["total_init"]/1e4:>8.0f}만'
              f'  {c["total_now"]/1e4:>8.0f}만'
              f'  {ret_str:>8}')

    # 거래 성과
    print(f'\n  {"버전":<22} {"거래수":>6} {"승률":>7} {"PF":>6} '
          f'{"기대값":>9} {"평균승":>9} {"평균패":>9} {"연속손":>6}')
    print(f'  {sep[:80]}')
    for v in VERSIONS:
        s = all_stats[v]['stats']
        if s.get('trades', 0) == 0:
            print(f'  {VERSION_NAMES[v]:<22}  {"(거래없음)"}')
            continue
        print(f'  {VERSION_NAMES[v]:<22}'
              f'  {s["trades"]:>6d}'
              f'  {s["win_rate"]:>6.1f}%'
              f'  {str(s["pf"]):>6}'
              f'  {s["expectancy"]:>+9,.0f}'
              f'  {s["avg_win"]:>+9,.0f}'
              f'  {s["avg_loss"]:>+9,.0f}'
              f'  {s["max_streak"]:>6d}')

    # 총 실현손익
    print(f'\n  {"버전":<22} {"총 실현손익":>14}')
    print(f'  {sep[:45]}')
    for v in VERSIONS:
        s = all_stats[v]['stats']
        if s.get('trades', 0) == 0:
            continue
        pnl = s.get('total_pnl', 0)
        print(f'  {VERSION_NAMES[v]:<22}  {pnl:>+14,.0f}원')

    print('\n' + '=' * 80)

    # 최우수 버전 판단
    ranked = [(v, all_stats[v]['stats'].get('total_pnl', -999_999_999))
              for v in VERSIONS
              if all_stats[v]['stats'].get('trades', 0) > 0]
    if ranked:
        ranked.sort(key=lambda x: x[1], reverse=True)
        best_v, best_pnl = ranked[0]
        print(f'\n  ★ 현재 최우수 버전: [{best_v.upper()}] {VERSION_NAMES[best_v]}'
              f'  ({best_pnl:+,.0f}원)')
    print()


if __name__ == '__main__':
    print_comparison()
