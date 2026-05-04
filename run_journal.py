# -*- coding: utf-8 -*-
"""
Warren Trading Bot — 자동 투자일지 생성기
==========================================
실행 시각에 따라 3종 세션 자동 생성:
  07:00  아침 브리핑  (시장 현황 + 오늘 전략 + 오픈 포지션)
  17:00  KR 마감 복기 (KR 결과 + 전략 수정 + Lessons Learned → US 반영)
  21:00  전체 복기    (하루 결과 + 최종 전략 수정 + 내일 전략)

사용법:
  python run_journal.py              # 시각 자동 감지
  python run_journal.py --session morning
  python run_journal.py --session afternoon
  python run_journal.py --session evening
"""
import sys, json, os, argparse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    # Windows 콘솔 코드페이지 UTF-8 강제 설정
    import os
    os.system('chcp 65001 > nul')

BASE = Path('C:/WarrenTradingActivebot-1.0.0/WarrenTradingActivebot-1.0.0')
JOURNAL_DIR = BASE / 'logs' / 'journal'
PORTFOLIO_PATH = BASE / 'logs' / 'paper_portfolio.json'
POSITIONS_PATH = BASE / 'logs' / 'paper_positions.json'
TRADES_PATH    = BASE / 'logs' / 'paper_trades.csv'
STRATEGY_PATH  = BASE / 'logs' / 'strategy_adjustments.json'

JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M')

def today_str():
    return datetime.now().strftime('%Y-%m-%d')

def detect_session(hour: int) -> str:
    if 6 <= hour < 13:
        return 'morning'
    elif 13 <= hour < 19:
        return 'afternoon'
    else:
        return 'evening'

def next_journal_filename(session: str) -> Path:
    today = today_str()
    suffix = {'morning': '01', 'afternoon': '02', 'evening': '03'}[session]
    path = JOURNAL_DIR / f'{today}-{suffix}.md'
    # 충돌 방지: 이미 있으면 다음 번호
    n = int(suffix)
    while path.exists():
        n += 1
        path = JOURNAL_DIR / f'{today}-{n:02d}.md'
    return path

def load_json(path: Path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def load_portfolio():
    return load_json(PORTFOLIO_PATH, {})

def load_positions():
    data = load_json(POSITIONS_PATH, {'positions': []})
    return data.get('positions', [])

def load_today_trades():
    """오늘 날짜 거래만 반환"""
    today = today_str()
    trades = []
    try:
        import csv
        with open(TRADES_PATH, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if today in row.get('time', ''):
                    trades.append(row)
    except Exception:
        pass
    return trades

def fetch_macro():
    """Yahoo Finance v8 API로 주요 지표 조회"""
    tickers = {
        'VIX':  '^VIX',
        'BTC':  'BTC-USD',
        'ETH':  'ETH-USD',
        'SOL':  'SOL-USD',
        'XRP':  'XRP-USD',
        'DOGE': 'DOGE-USD',
        'NVDA': 'NVDA',
        'AMD':  'AMD',
    }
    prices = {}
    for label, sym in tickers.items():
        try:
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            r = data['chart']['result'][0]
            close = r['indicators']['quote'][0]['close']
            prices[label] = close[-1] if close[-1] else close[-2]
        except Exception:
            prices[label] = None
    return prices

def macro_regime(vix):
    if vix is None:
        return 'UNKNOWN'
    if vix > 35:
        return 'HALT'
    elif vix > 25:
        return 'DEFENSIVE'
    elif vix > 20:
        return 'NORMAL'
    else:
        return 'AGGRESSIVE'

def fmt_price(v, decimals=2):
    if v is None:
        return 'N/A'
    if v >= 1000:
        return f'{v:,.0f}'
    elif v >= 10:
        return f'{v:,.2f}'
    else:
        return f'{v:.4f}'

def calc_total_assets(portfolio: dict, positions: list) -> dict:
    """시장별 총 자산 = 잔여현금 + 오픈포지션 합계 (실현손익은 이미 capital에 반영됨)"""
    invested: dict = {'KR': 0, 'US': 0, 'CRYPTO': 0}
    for p in positions:
        mkt = p.get('market', 'KR')
        if mkt in invested:
            invested[mkt] += p.get('size_krw', 0)
    result = {}
    for mkt in ('KR', 'US', 'CRYPTO'):
        cash = portfolio.get('capital', {}).get(mkt, 0)
        result[mkt] = {
            'cash': cash,
            'invested': invested[mkt],
            'total': cash + invested[mkt],
            'initial': portfolio.get('initial_capital', {}).get(mkt, 0),
            'realized_pnl': portfolio.get('realized_pnl', {}).get(mkt, 0),
        }
    return result


def positions_summary(positions):
    if not positions:
        return '오픈 포지션 없음'
    lines = []
    for p in positions:
        entry = p.get('entry', 0)
        tp = p.get('tp', 0)
        sl = p.get('sl', 0)
        tp_pct = p.get('tp_pct', 0)
        sl_pct = p.get('sl_pct', 0)
        lines.append(
            f"  - {p.get('name','?')}({p.get('ticker','?')}) [{p.get('timeframe','?')}] "
            f"{p.get('signal_type','?')} | 진입={fmt_price(entry)} | "
            f"TP={tp_pct:+.1f}% | SL={sl_pct:+.1f}% | 사이즈={int(p.get('size_krw',0)):,}원"
        )
    return '\n'.join(lines)

def trades_summary(trades, label='오늘'):
    if not trades:
        return f'{label} 체결 거래 없음'
    wins = [t for t in trades if t.get('result') == 'WIN']
    losses = [t for t in trades if t.get('result') == 'LOSS']
    lines = [f'총 {len(trades)}건 | 승 {len(wins)}건 | 패 {len(losses)}건']
    for t in trades:
        result_icon = '✅' if t.get('result') == 'WIN' else '❌'
        lines.append(
            f"  {result_icon} {t.get('name','?')}({t.get('ticker','?')}) "
            f"[{t.get('timeframe','?')}] {t.get('signal_type','?')} | "
            f"net={float(t.get('net_pnl_krw', 0)):+,.0f}원 | "
            f"수익률={float(t.get('net_pnl_pct', 0)):+.2f}%"
        )
    return '\n'.join(lines)

AFTERNOON_REVIEW_PATH = BASE / 'logs' / 'afternoon_review.json'


def save_afternoon_review(data: dict):
    """17:00 복기 결과를 저장 → 21:00 Lessons Learned에서 참조"""
    try:
        with open(AFTERNOON_REVIEW_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_afternoon_review() -> dict:
    """21:00에 17:00 복기 결과 로드"""
    return load_json(AFTERNOON_REVIEW_PATH, {})


def analyze_strategy_performance(trades: list) -> dict:
    """전략별 성과 분석 — 어떤 전략이 오늘 더 우수했는지 계산.

    Returns:
        {strategy_name: {wins, losses, win_rate, total_pnl, avg_pnl}}
    """
    from collections import defaultdict
    stats: dict = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_pnl': 0.0})

    for t in trades:
        strat = t.get('signal_type', 'UNKNOWN')
        pnl   = float(t.get('pnl_pct', t.get('net_pnl_pct', 0)))
        if t.get('result') == 'WIN':
            stats[strat]['wins'] += 1
        else:
            stats[strat]['losses'] += 1
        stats[strat]['total_pnl'] += pnl

    result = {}
    for strat, s in stats.items():
        total = s['wins'] + s['losses']
        result[strat] = {
            'wins':      s['wins'],
            'losses':    s['losses'],
            'total':     total,
            'win_rate':  round(s['wins'] / total * 100, 1) if total > 0 else 0,
            'total_pnl': round(s['total_pnl'], 2),
            'avg_pnl':   round(s['total_pnl'] / total, 2) if total > 0 else 0,
        }
    # 승률 내림차순 정렬
    return dict(sorted(result.items(), key=lambda x: x[1]['win_rate'], reverse=True))


def load_strategy_adjustments():
    return load_json(STRATEGY_PATH, {
        'version': 'v4.0',
        'last_updated': '',
        'kr_strategy': 'BB반등(RSI<35+BB하단) 1H',
        'us_strategy': 'BB반등+Momentum 1H',
        'crypto_strategy': 'FVG+OB 4H R:R1:3',
        'adjustments': [],
        'active_filters': [],
        'disabled_tickers': []
    })

def save_strategy_adjustments(adj):
    adj['last_updated'] = now_str()
    with open(STRATEGY_PATH, 'w', encoding='utf-8') as f:
        json.dump(adj, f, ensure_ascii=False, indent=2)


# ── 세션별 일지 생성 ─────────────────────────────────────────────────────────

def make_morning(macro, portfolio, positions, adj):
    """07:00 아침 브리핑"""
    vix = macro.get('VIX')
    regime = macro_regime(vix)
    pos_count = len(positions)
    assets = calc_total_assets(portfolio, positions)
    init_total = sum(a['initial'] for a in assets.values())
    port_total = sum(a['total'] for a in assets.values())
    total_pnl  = port_total - init_total

    wins   = portfolio.get('wins', 0)
    losses = portfolio.get('losses', 0)
    total_t= portfolio.get('total_trades', 0)
    wr     = wins / total_t * 100 if total_t > 0 else 0

    adj_list = adj.get('adjustments', [])
    latest_adj = adj_list[-3:] if adj_list else []

    lines = [
        f'# Warren Trading Journal — 아침 브리핑',
        f'**날짜:** {today_str()} (07:00 KST)',
        f'**작성 시각:** {now_str()} KST',
        f'**세션:** 아침 브리핑 — 오늘 시장 현황 + 전략 확인',
        '',
        '---',
        '',
        '## 1. 시장 현황',
        '| 지표 | 수치 | 상태 |',
        '|------|------|------|',
        f'| 매크로 국면 | **{regime}** | VIX={fmt_price(vix, 1)} |',
        f'| BTC | {fmt_price(macro.get("BTC"))} | - |',
        f'| ETH | {fmt_price(macro.get("ETH"))} | - |',
        f'| SOL | {fmt_price(macro.get("SOL"))} | - |',
        f'| XRP | {fmt_price(macro.get("XRP"))} | - |',
        f'| NVDA | {fmt_price(macro.get("NVDA"))} | - |',
        f'| AMD | {fmt_price(macro.get("AMD"))} | - |',
        f'| KR 시장 | 09:00 KST 오픈 예정 | 장 개장 2시간 전 브리핑 |',
        f'| US 시장 | 22:30 KST 오픈 예정 | 야간 |',
        '',
        '---',
        '',
        '## 2. 포트폴리오 현황',
        '| 시장 | 총 자산 | 가용현금 | 투자중 | 초기자본 | 실현손익 |',
        '|------|--------|--------|------|--------|--------|',
    ]
    for mkt in ('KR', 'US', 'CRYPTO'):
        a = assets[mkt]
        lines.append(
            f'| {mkt} | {a["total"]:,.0f}원 | {a["cash"]:,.0f}원 | '
            f'{a["invested"]:,.0f}원 | {a["initial"]:,.0f}원 | {a["realized_pnl"]:+,.0f}원 |'
        )
    lines += [
        f'| **합계** | **{port_total:,.0f}원** | - | - | **{init_total:,.0f}원** | **{total_pnl:+,.0f}원** |',
        '',
        f'- 누적 거래: {total_t}건 | 승률: {wr:.1f}% ({wins}승 {losses}패)',
        '',
        '---',
        '',
        f'## 3. 오픈 포지션 ({pos_count}개)',
        positions_summary(positions),
        '',
        '---',
        '',
        '## 4. 오늘 전략 포인트',
        '',
        f'**매크로 국면: {regime}**',
    ]

    if regime == 'HALT':
        lines += [
            '> ⛔ HALT — 전면 거래 차단. 오늘은 관망만.',
        ]
    elif regime == 'DEFENSIVE':
        lines += [
            '> ⚠️ DEFENSIVE — 품질 필터 3점+ 신호만 진입. 포지션 사이즈 50% 축소.',
        ]
    elif regime == 'NORMAL':
        lines += [
            '> ✅ NORMAL — 정상 운용. BB반등 + FVG+OB 4H 전략 가동.',
        ]
    else:
        lines += [
            '> 🚀 AGGRESSIVE — 공격적 운용 가능. 신호 품질 검토 후 진입.',
        ]

    lines += [
        '',
        '**시장별 오늘 전략:**',
        '| 시장 | 전략 | 타이밍 | 주목 종목 |',
        '|------|------|--------|---------|',
        f'| KR | BB반등(RSI<35+BB하단) 1H | 09:05~15:20 | SK텔레콤, 카카오, 코웨이, 현대차 |',
        f'| US | BB반등+Momentum 1H | 22:35~ | AMD, MU, NVDA, AVGO, MSTR |',
        f'| CRYPTO | FVG+OB 4H R:R1:3 | 24시간 | BTC, SOL, DOGE, XRP |',
    ]

    if latest_adj:
        lines += ['', '**최근 전략 조정 사항 (반영 중):**']
        for a in latest_adj:
            lines.append(f'- [{a.get("date","")}] {a.get("content","")}')

    lines += [
        '',
        '---',
        '',
        '## 5. 오늘 체크리스트',
        '- [ ] 09:05 KR BB반등 신호 스캔',
        '- [ ] 10:00 KR 중반 스캔',
        '- [ ] 13:00 KR 오후 스캔',
        '- [ ] 15:20 포지션 청산 확인',
        '- [ ] 17:00 KR 마감 복기 일지 작성',
        '- [ ] 21:00 전체 복기 + 미국장 전략 확정',
        '- [ ] 22:35 US 장 신호 스캔',
        f'- [ ] CRYPTO 4H 신호 상시 모니터링 (BTC={fmt_price(macro.get("BTC"))}, SOL={fmt_price(macro.get("SOL"))})',
        '',
        '---',
        '',
        f'*작성: Warren Bot 자동 생성 | {now_str()} KST*',
    ]
    return '\n'.join(lines)


def make_afternoon(macro, portfolio, positions, trades_today, adj):
    """17:00 KR 마감 복기"""
    vix = macro.get('VIX')
    regime = macro_regime(vix)
    pos_count = len(positions)
    assets = calc_total_assets(portfolio, positions)
    init_total = sum(a['initial'] for a in assets.values())
    port_total = sum(a['total'] for a in assets.values())
    total_pnl  = port_total - init_total

    wins   = portfolio.get('wins', 0)
    losses = portfolio.get('losses', 0)
    total_t= portfolio.get('total_trades', 0)
    wr     = wins / total_t * 100 if total_t > 0 else 0

    kr_trades  = [t for t in trades_today if t.get('market') == 'KR']
    kr_wins    = [t for t in kr_trades if t.get('result') == 'WIN']
    kr_losses  = [t for t in kr_trades if t.get('result') == 'LOSS']
    kr_net     = sum(float(t.get('net_pnl_krw', 0)) for t in kr_trades)

    # 전략 수정 분석
    loss_patterns = []
    for t in kr_losses:
        loss_patterns.append(f'{t.get("name","?")}({t.get("signal_type","?")}) {float(t.get("net_pnl_pct",0)):+.2f}%')

    lines = [
        f'# Warren Trading Journal — KR 마감 복기',
        f'**날짜:** {today_str()} (17:00 KST)',
        f'**작성 시각:** {now_str()} KST',
        f'**세션:** KR 마감 복기 — 결과 분석 + 전략 수정 → US 장 반영',
        '',
        '---',
        '',
        '## 1. 시장 현황',
        '| 지표 | 수치 |',
        '|------|------|',
        f'| 매크로 국면 | **{regime}** (VIX={fmt_price(vix,1)}) |',
        f'| BTC | {fmt_price(macro.get("BTC"))} |',
        f'| ETH | {fmt_price(macro.get("ETH"))} |',
        f'| SOL | {fmt_price(macro.get("SOL"))} |',
        f'| KR 시장 | 15:30 마감 완료 |',
        f'| US 시장 | 22:30 KST 오픈 예정 |',
        '',
        '---',
        '',
        '## 2. KR 오늘 거래 결과',
        f'### 체결 내역 ({len(kr_trades)}건)',
        trades_summary(kr_trades, 'KR 오늘'),
        '',
        f'### KR 일일 손익: **{kr_net:+,.0f}원**',
        f'- 승: {len(kr_wins)}건 | 패: {len(kr_losses)}건 | ',
        f'- 승률: {len(kr_wins)/len(kr_trades)*100:.1f}%' if kr_trades else '- 거래 없음',
        '',
        '---',
        '',
        '## 3. 포트폴리오 현황 (17:00 기준)',
        '| 시장 | 총 자산 | 가용현금 | 투자중 | 초기자본 | 실현손익 |',
        '|------|--------|--------|------|--------|--------|',
        f'| KR | {assets["KR"]["total"]:,.0f}원 | {assets["KR"]["cash"]:,.0f}원 | {assets["KR"]["invested"]:,.0f}원 | {assets["KR"]["initial"]:,.0f}원 | {assets["KR"]["realized_pnl"]:+,.0f}원 |',
        f'| US | {assets["US"]["total"]:,.0f}원 | {assets["US"]["cash"]:,.0f}원 | {assets["US"]["invested"]:,.0f}원 | {assets["US"]["initial"]:,.0f}원 | {assets["US"]["realized_pnl"]:+,.0f}원 |',
        f'| CRYPTO | {assets["CRYPTO"]["total"]:,.0f}원 | {assets["CRYPTO"]["cash"]:,.0f}원 | {assets["CRYPTO"]["invested"]:,.0f}원 | {assets["CRYPTO"]["initial"]:,.0f}원 | {assets["CRYPTO"]["realized_pnl"]:+,.0f}원 |',
        f'| **합계** | **{port_total:,.0f}원** | - | - | **{init_total:,.0f}원** | **{total_pnl:+,.0f}원** |',
        '',
        f'- 누적: {total_t}건 | 승률: {wr:.1f}% ({wins}승 {losses}패)',
        f'- 오픈 포지션: {pos_count}개',
        '',
        '---',
        '',
        f'## 4. 오픈 포지션 ({pos_count}개)',
        positions_summary(positions),
        '',
        '---',
        '',
        '## 5. 패턴 분석 — 오늘 손실 원인',
    ]

    if kr_losses:
        lines += [
            '| 종목 | 신호 | 손익 | 원인 추정 |',
            '|------|------|------|---------|',
        ]
        for t in kr_losses:
            lines.append(
                f'| {t.get("name","?")} | {t.get("signal_type","?")} | '
                f'{float(t.get("net_pnl_pct",0)):+.2f}% | 분석 필요 |'
            )
    else:
        lines += ['KR 손실 거래 없음 또는 거래 없음']

    lines += [
        '',
        '---',
        '',
        '## 6. 전략 수정 (US 장부터 반영)',
        '',
        '### 수정 내용',
        '> 아래 수정사항은 오늘 22:30 US 장 오픈부터 즉시 적용',
        '',
        '| 항목 | 기존 | 수정 | 이유 |',
        '|------|------|------|------|',
        '| (자동 분석 기반으로 채워주세요) | - | - | - |',
        '',
        '### US 장 집중 종목',
        '| 종목 | 전략 | 조건 | 주목 이유 |',
        '|------|------|------|---------|',
        '| AMD | BB반등 | RSI<35 + BB하단 | BB반등 WR 87.5% |',
        '| MU | SuperTrend | 추세 전환 | WR 80% |',
        '| NVDA | MACD | 골든크로스 | WR 72.7% |',
        '',
        '---',
        '',
        '## 7. LESSONS LEARNED — 오늘의 교훈',
        '',
        f'**{today_str()} KR 장 복기:**',
        '',
    ]

    if not kr_trades:
        lines += ['1. 오늘 KR 거래 없음 — 신호 미발생 또는 필터 미통과']
    else:
        lines += [
            f'1. KR 승률 {len(kr_wins)/len(kr_trades)*100:.0f}% — {"양호" if len(kr_wins)/len(kr_trades) >= 0.55 else "부진, 원인 분석 필요"}',
        ]
        if kr_losses:
            lines += [
                f'2. 손실 종목: {", ".join(loss_patterns)} — 진입 조건 재검토',
                '3. 패배 패턴 공통점: (직접 분석 후 기록)',
            ]
        if kr_wins:
            win_patterns = [f'{t.get("name","?")}({t.get("signal_type","?")}) {float(t.get("net_pnl_pct",0)):+.2f}%' for t in kr_wins]
            lines += [
                f'4. 수익 종목: {", ".join(win_patterns)} — 패턴 강화',
            ]

    # ── 전략별 성과 분석 (17시 핵심 작업) ────────────────
    strat_perf = analyze_strategy_performance(trades_today)
    lines += [
        '',
        '---',
        '',
        '## 8. 전략별 성과 비교 (오늘 어떤 전략이 우수했나)',
        '| 전략 | 거래수 | 승 | 패 | 승률 | 평균손익 | 총손익 |',
        '|------|-------|---|---|-----|---------|-------|',
    ]
    if strat_perf:
        for strat, s in strat_perf.items():
            lines.append(
                f'| {strat} | {s["total"]}건 | {s["wins"]}승 | {s["losses"]}패 | '
                f'{s["win_rate"]:.1f}% | {s["avg_pnl"]:+.2f}% | {s["total_pnl"]:+.2f}% |'
            )
        best = list(strat_perf.keys())[0]
        worst = list(strat_perf.keys())[-1]
        lines += [
            '',
            f'- **오늘 최우수 전략**: {best} (승률 {strat_perf[best]["win_rate"]:.1f}%)',
            f'- **오늘 최하위 전략**: {worst} (승률 {strat_perf[worst]["win_rate"]:.1f}%)',
            f'- **개선 방향**: {worst} 전략 진입 조건 재검토 → 내일부터 반영',
        ]
    else:
        lines += ['오늘 체결 거래 없음 — 전략 비교 불가']

    lines += [
        '',
        '---',
        '',
        '## 9. 내일 KR 주목 종목',
        '| 종목 | 현재 RSI | BB 위치 | 기대 |',
        '|------|---------|--------|------|',
        '| SK텔레콤(017670) | - | - | BB반등 근접시 진입 대기 |',
        '| 카카오(035720) | - | - | RSI 과매도 감시 |',
        '| 코웨이(021240) | - | - | BB하단 접근 확인 |',
        '',
        '---',
        '',
        f'*작성: Warren Bot 자동 생성 | {now_str()} KST*',
    ]

    # 17:00 복기 결과 저장 → 21:00 Lessons Learned에서 참조
    save_afternoon_review({
        'date':         today_str(),
        'kr_trades':    len(kr_trades),
        'kr_wr':        round(len(kr_wins) / len(kr_trades) * 100, 1) if kr_trades else 0,
        'kr_net':       sum(float(t.get('pnl_krw', 0)) for t in kr_trades),
        'strategy_perf': strat_perf,
        'best_strategy': list(strat_perf.keys())[0] if strat_perf else '',
        'worst_strategy': list(strat_perf.keys())[-1] if strat_perf else '',
        'key_lessons':  [
            f'최우수전략: {list(strat_perf.keys())[0]}' if strat_perf else '거래 없음',
        ],
    })

    return '\n'.join(lines)


def make_evening(macro, portfolio, positions, trades_today, adj):
    """21:00 전체 복기 + 내일 전략"""
    vix = macro.get('VIX')
    regime = macro_regime(vix)
    pos_count = len(positions)
    assets = calc_total_assets(portfolio, positions)
    init_total = sum(a['initial'] for a in assets.values())
    port_total = sum(a['total'] for a in assets.values())
    total_pnl  = port_total - init_total
    total_pnl_pct = total_pnl / init_total * 100 if init_total > 0 else 0

    wins   = portfolio.get('wins', 0)
    losses = portfolio.get('losses', 0)
    total_t= portfolio.get('total_trades', 0)
    wr     = wins / total_t * 100 if total_t > 0 else 0

    kr_trades  = [t for t in trades_today if t.get('market') == 'KR']
    us_trades  = [t for t in trades_today if t.get('market') == 'US']
    cr_trades  = [t for t in trades_today if t.get('market') == 'CRYPTO']
    today_net  = sum(float(t.get('net_pnl_krw', 0)) for t in trades_today)

    all_wins  = [t for t in trades_today if t.get('result') == 'WIN']
    all_loss  = [t for t in trades_today if t.get('result') == 'LOSS']
    today_wr  = len(all_wins) / len(trades_today) * 100 if trades_today else 0

    lines = [
        f'# Warren Trading Journal — 전체 복기 + 미국장 전략',
        f'**날짜:** {today_str()} (21:00 KST)',
        f'**작성 시각:** {now_str()} KST',
        f'**세션:** 전체 복기 — 오늘 결과 총정리 + 전략 수정 → 미국장(22:30~) 반영',
        '',
        '---',
        '',
        '## 1. 시장 현황 (21:00 기준)',
        '| 지표 | 수치 | 상태 |',
        '|------|------|------|',
        f'| 매크로 국면 | **{regime}** | VIX={fmt_price(vix,1)} |',
        f'| BTC | {fmt_price(macro.get("BTC"))} | - |',
        f'| ETH | {fmt_price(macro.get("ETH"))} | - |',
        f'| SOL | {fmt_price(macro.get("SOL"))} | - |',
        f'| XRP | {fmt_price(macro.get("XRP"))} | - |',
        f'| DOGE | {fmt_price(macro.get("DOGE"))} | - |',
        f'| NVDA | {fmt_price(macro.get("NVDA"))} | - |',
        f'| AMD | {fmt_price(macro.get("AMD"))} | - |',
        f'| KR 시장 | 마감 완료 | - |',
        f'| US 시장 | 22:30 KST 오픈 예정 | 1.5시간 후 |',
        '',
        '---',
        '',
        '## 2. 오늘 거래 결과 총정리',
        f'### 일일 성과 요약',
        '| 시장 | 거래수 | 승 | 패 | 일일손익 |',
        '|------|-------|---|---|---------|',
        f'| KR | {len(kr_trades)}건 | {len([t for t in kr_trades if t.get("result")=="WIN"])}승 | {len([t for t in kr_trades if t.get("result")=="LOSS"])}패 | {sum(float(t.get("net_pnl_krw",0)) for t in kr_trades):+,.0f}원 |',
        f'| US | {len(us_trades)}건 | {len([t for t in us_trades if t.get("result")=="WIN"])}승 | {len([t for t in us_trades if t.get("result")=="LOSS"])}패 | {sum(float(t.get("net_pnl_krw",0)) for t in us_trades):+,.0f}원 |',
        f'| CRYPTO | {len(cr_trades)}건 | {len([t for t in cr_trades if t.get("result")=="WIN"])}승 | {len([t for t in cr_trades if t.get("result")=="LOSS"])}패 | {sum(float(t.get("net_pnl_krw",0)) for t in cr_trades):+,.0f}원 |',
        f'| **합계** | **{len(trades_today)}건** | **{len(all_wins)}승** | **{len(all_loss)}패** | **{today_net:+,.0f}원** |',
        '',
        f'**오늘 승률: {today_wr:.1f}%** (목표 55%+ {"✅" if today_wr >= 55 else "❌"})',
        '',
        '### 체결 상세',
        trades_summary(trades_today, '오늘 전체'),
        '',
        '---',
        '',
        '## 3. 누적 포트폴리오 현황',
        '| 시장 | 총 자산 | 가용현금 | 투자중 | 초기자본 | 실현손익 | 수익률 |',
        '|------|--------|--------|------|--------|--------|-------|',
    ]

    for mkt in ('KR', 'US', 'CRYPTO'):
        a = assets[mkt]
        pct = (a['total'] - a['initial']) / a['initial'] * 100 if a['initial'] else 0
        lines.append(
            f'| {mkt} | {a["total"]:,.0f}원 | {a["cash"]:,.0f}원 | '
            f'{a["invested"]:,.0f}원 | {a["initial"]:,.0f}원 | '
            f'{a["realized_pnl"]:+,.0f}원 | {pct:+.2f}% |'
        )

    lines += [
        f'| **합계** | **{port_total:,.0f}원** | - | - | **{init_total:,.0f}원** | **{total_pnl:+,.0f}원** | **{total_pnl_pct:+.2f}%** |',
        '',
        f'- 누적: {total_t}건 | 승률: {wr:.1f}% ({wins}승 {losses}패)',
        f'- 오픈 포지션: {pos_count}개',
        '',
        '---',
        '',
        f'## 4. 오픈 포지션 ({pos_count}개) — 미국장 모니터링',
        positions_summary(positions),
        '',
        '---',
        '',
        '## 5. 전략 수정 — 오늘 미국장(22:30~)부터 즉시 적용',
        '',
        '### 수정 결정',
        '| 항목 | 기존 | 수정 후 | 근거 |',
        '|------|------|--------|------|',
        '| (오늘 결과 분석 후 기록) | - | - | - |',
        '',
        '### US 집중 공략 종목 (오늘 밤)',
        '| 종목 | 전략 | 진입 조건 | 목표 |',
        '|------|------|---------|------|',
        '| AMD | BB반등 | RSI<35 + BB하단 터치 | TP BB중앙 (+2~3%) |',
        '| MU | SuperTrend | 추세선 위 반등 | TP +2% |',
        '| NVDA | MACD | 골든크로스 확인 | TP +1.5% |',
        '| AVGO | SuperTrend | 지지선 확인 | TP +2.5% |',
        '',
        '### CRYPTO 4H 모니터링 (24시간)',
        '| 종목 | 현재가 | 전략 조건 | 기대 |',
        '|------|-------|---------|------|',
        f'| BTC | {fmt_price(macro.get("BTC"))} | FVG/OB 존 접근시 | TP +3% (R:R 1:3) |',
        f'| SOL | {fmt_price(macro.get("SOL"))} | FVG/OB 존 접근시 | TP +3% (R:R 1:3) |',
        f'| DOGE | {fmt_price(macro.get("DOGE"))} | FVG/OB 존 접근시 | TP +3% (R:R 1:3) |',
        f'| XRP | {fmt_price(macro.get("XRP"))} | FVG/OB 존 접근시 | TP +3% (R:R 1:3) |',
        '',
        '---',
        '',
        '## 6. LESSONS LEARNED — 오늘의 핵심 교훈',
        '',
    ]

    lesson_n = 1
    if not trades_today:
        lines += [f'{lesson_n}. 오늘 체결 거래 없음 — 신호 품질 기준 통과 종목 부재']
        lesson_n += 1
    else:
        if today_wr >= 55:
            lines += [f'{lesson_n}. 오늘 승률 {today_wr:.0f}% — 목표(55%) 초과 달성, 현재 전략 유효']
        else:
            lines += [f'{lesson_n}. 오늘 승률 {today_wr:.0f}% — 목표(55%) 미달, 진입 조건 강화 검토']
        lesson_n += 1

        if all_loss:
            lines += [f'{lesson_n}. 패배 거래 공통점: (직접 분석 기록) — 다음 신호에서 필터 적용']
            lesson_n += 1
        if all_wins:
            lines += [f'{lesson_n}. 수익 거래 공통점: (직접 분석 기록) — 이 패턴 반복 집중']
            lesson_n += 1

    lines += [
        f'{lesson_n}. BB반등 원칙: RSI<35 확인 없으면 진입 안 함',
        f'{lesson_n+1}. CRYPTO 4H R:R 1:3 — BEP=25%, WR 27~32% 이상이면 장기적 수익',
        f'{lesson_n+2}. 포지션당 2% 리스크 원칙 — 절대 초과 금지',
        '',
        '---',
        '',
        '## 7. 오늘 논의 & 전략 개선 기록 (Lessons Applied)',
        '',
        '### TP 연장 전략 (2026-04-30 확정 적용)',
        '| 단계 | 조건 | 처리 |',
        '|------|------|------|',
        '| TP1 도달 | 일봉 3개(RSI<75/MACD/양봉) + 15m 3개(EMA정렬/CHoCH없음/RSI>50) 중 4/6 이상 | TP2 연장, SL→TP1 |',
        '| TP2 도달 | 동일 조건 5/6 이상 | TP3 연장, SL→TP2 |',
        '| TP3 도달 | 조건 무관 | 무조건 전량 청산 |',
        '| 15m 베어리시 CHoCH | TP2 이상 포지션에서 감지 시 | 즉시 시장가 청산 |',
        '| TP2 반락 | SL=TP1 이므로 최소 +4% 확보 상태 | SL에서 자동 청산 |',
        '',
        '### 17:00 KR 복기 결과 요약',
    ]

    # 17시 복기 결과 자동 참조
    ar = load_afternoon_review()
    if ar.get('date') == today_str():
        sp = ar.get('strategy_perf', {})
        lines += [
            f'- KR 거래: {ar.get("kr_trades",0)}건 | 승률: {ar.get("kr_wr",0):.1f}% | 손익: {ar.get("kr_net",0):+,.0f}원',
            f'- 최우수 전략: **{ar.get("best_strategy","없음")}** | 최하위: {ar.get("worst_strategy","없음")}',
        ]
        if sp:
            lines += ['', '**전략별 성과:**', '| 전략 | 승률 | 평균손익 |', '|------|-----|---------|']
            for strat, s in sp.items():
                lines.append(f'| {strat} | {s["win_rate"]:.1f}% | {s["avg_pnl"]:+.2f}% |')
        lines += [
            '',
            f'**내일 개선 방향**: {ar.get("worst_strategy","?")} 전략 진입 조건 강화',
        ]
    else:
        lines += ['- 17:00 복기 미실행 (수동 복기 필요)']

    lines += [
        '',
        '### 오늘 적용된 신규 전략',
        '### KR/US/CRYPTO 현재가 조회 체계 (2026-04-30 확정)',
        '- KR: KIS API 1순위 → FinanceDataReader fallback',
        '- CRYPTO: pyupbit 1순위 → yfinance fallback',
        '- US: yfinance',
        '',
        '### 전략 레지스트리 구조 (재발 방지)',
        '- _KR_STRATEGY_FN / _US_STRATEGY_FN 딕셔너리 1곳만 수정',
        '- 디스패처 함수 수정 불필요 — 누락 사고 원천 차단',
        '',
        '',
        '## 7. 내일 전략 (pre-planning)',
        '',
        '**KR (09:05~15:20)**',
        '- BB반등: RSI<35 + BB하단 터치 확인 필수',
        '- 보조전략: 하나금융(MACD), 삼성중공업(SuperTrend)',
        '- 주목: SK텔레콤(017670), 카카오(035720) RSI 하락 추이 감시',
        '',
        '**US (22:30~)**',
        '- BB반등: AMD, MU, MSTR 우선',
        '- Momentum: NVDA, AVGO 추세 확인',
        '- 1건당 최대 사이즈: 100만원 (리스크 2%)',
        '',
        '**CRYPTO (24시간)**',
        f'- BTC FVG/OB 존 확인 (현재가={fmt_price(macro.get("BTC"))})',
        f'- SOL 지지 구간 모니터링 (현재가={fmt_price(macro.get("SOL"))})',
        '- 4H 봉 마감 시 신호 스캔 자동 실행',
        '',
        '---',
        '',
        f'*작성: Warren Bot 자동 생성 | {now_str()} KST*',
    ]
    return '\n'.join(lines)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', choices=['morning', 'afternoon', 'evening'],
                        help='세션 강제 지정 (기본: 시각 자동 감지)')
    args = parser.parse_args()

    hour = datetime.now().hour
    session = args.session or detect_session(hour)

    session_name = {'morning': '아침 브리핑', 'afternoon': 'KR 마감 복기', 'evening': '전체 복기'}[session]
    print(f'[Warren Journal] {now_str()} — {session_name} 생성 중...')

    # 데이터 수집
    print('  매크로 데이터 조회...')
    macro = fetch_macro()
    print(f'  BTC={fmt_price(macro.get("BTC"))} | VIX={fmt_price(macro.get("VIX"),1)} | 국면={macro_regime(macro.get("VIX"))}')

    portfolio = load_portfolio()
    positions = load_positions()
    trades_today = load_today_trades()
    adj = load_strategy_adjustments()

    print(f'  포트폴리오: 자본 {sum(portfolio.get("capital",{}).values()):,.0f}원')
    print(f'  오픈 포지션: {len(positions)}개 | 오늘 거래: {len(trades_today)}건')

    # 일지 생성
    if session == 'morning':
        content = make_morning(macro, portfolio, positions, adj)
    elif session == 'afternoon':
        content = make_afternoon(macro, portfolio, positions, trades_today, adj)
    else:
        content = make_evening(macro, portfolio, positions, trades_today, adj)

    # 저장
    path = next_journal_filename(session)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 대시보드 갱신 트리거 (07:00/17:00/21:00 저널 완료 시 자동 반영)
    trigger_path = BASE / 'logs' / 'dashboard_refresh.json'
    try:
        import json as _json
        with open(trigger_path, 'w', encoding='utf-8') as tf:
            _json.dump({
                'last_updated': now_str(),
                'session':      session,
                'journal_file': str(path.name),
            }, tf, ensure_ascii=False)
    except Exception:
        pass

    print(f'\n  일지 저장 완료: {path}')
    print(f'  세션: {session_name}')

    # 전략 조정 파일 초기화 (없으면 생성)
    if not STRATEGY_PATH.exists():
        save_strategy_adjustments(adj)
        print(f'  전략 조정 파일 생성: {STRATEGY_PATH}')

    return str(path)


if __name__ == '__main__':
    result = main()
    print(f'\n[완료] {result}')
