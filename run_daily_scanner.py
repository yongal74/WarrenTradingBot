# -*- coding: utf-8 -*-
"""
Warren Daily Market Scanner — 일일 종목 서칭
============================================
매일 KR / US / CRYPTO 에서 각 5종목씩 유망 후보를 발굴.
현재 운용 유니버스(18/10/4종목)를 넘어 확장 풀에서 스캔.

실행:
  python run_daily_scanner.py           # 전 시장 스캔
  python run_daily_scanner.py --market KR
  python run_daily_scanner.py --market US
  python run_daily_scanner.py --market CRYPTO

출력:
  - 콘솔 요약
  - logs/daily_scan/YYYY-MM-DD.json
  - 텔레그램 알림
"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os, json, argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

BASE      = Path(__file__).parent
SCAN_DIR  = BASE / 'logs' / 'daily_scan'
SCAN_DIR.mkdir(parents=True, exist_ok=True)

TOP_N = 5   # 시장별 최대 추천 종목 수

# ── 확장 유니버스 ────────────────────────────────────────────────────────────

# KR 확장 풀 (현재 운용 18종목 + 추가 후보 22종목 = 40종목)
KR_SCAN_POOL: dict[str, tuple[str, str]] = {
    # 운용 중 18종목
    '017670': ('SK텔레콤',        '017670.KS'),
    '035720': ('카카오',          '035720.KS'),
    '021240': ('코웨이',          '021240.KS'),
    '005380': ('현대차',          '005380.KS'),
    '010140': ('삼성중공업',      '010140.KS'),
    '086790': ('하나금융',        '086790.KS'),
    '034020': ('두산에너빌',      '034020.KS'),
    '272210': ('한화시스템',      '272210.KS'),
    '000660': ('SK하이닉스',      '000660.KS'),
    '058470': ('리노공업',        '058470.KS'),
    '064350': ('현대로템',        '064350.KS'),
    '128940': ('한미약품',        '128940.KS'),
    '012450': ('한화에어로스페이스','012450.KS'),
    '005930': ('삼성전자',        '005930.KS'),
    '009150': ('삼성전기',        '009150.KS'),
    '008060': ('대덕전자',        '008060.KS'),
    # 후보 추가 22종목
    '035420': ('네이버',          '035420.KS'),
    '323410': ('카카오뱅크',      '323410.KS'),
    '068270': ('셀트리온',        '068270.KS'),
    '207940': ('삼성바이오로직스','207940.KS'),
    '000270': ('기아',            '000270.KS'),
    '066570': ('LG전자',          '066570.KS'),
    '005490': ('POSCO홀딩스',     '005490.KS'),
    '030200': ('KT',              '030200.KS'),
    '032830': ('삼성생명',        '032830.KS'),
    '105560': ('KB금융',          '105560.KS'),
    '055550': ('신한지주',        '055550.KS'),
    '003550': ('LG',              '003550.KS'),
    '096770': ('SK이노베이션',    '096770.KS'),
    '011200': ('HMM',             '011200.KS'),
    '028260': ('삼성물산',        '028260.KS'),
    '010950': ('S-Oil',           '010950.KS'),
    '047050': ('포스코인터내셔널','047050.KS'),
    '018260': ('삼성에스디에스',  '018260.KS'),
    '006400': ('삼성SDI',         '006400.KS'),
    '373220': ('LG에너지솔루션',  '373220.KS'),
    '051910': ('LG화학',          '051910.KS'),
    '009830': ('한화솔루션',      '009830.KS'),
}

# US 확장 풀 (운용 10종목 + 후보 20종목 = 30종목)
US_SCAN_POOL: dict[str, str] = {
    # 운용 중 10종목
    'AMD': 'AMD', 'MU': 'MU', 'NVDA': 'NVDA', 'AVGO': 'AVGO', 'MSTR': 'MSTR',
    'LRCX': 'LRCX', 'AMZN': 'AMZN', 'SHOP': 'SHOP', 'GOOGL': 'GOOGL', 'TSLA': 'TSLA',
    # 후보 20종목
    'MSFT': 'MSFT', 'AAPL': 'AAPL', 'META': 'META', 'TSM': 'TSM',
    'PLTR': 'PLTR', 'COIN': 'COIN', 'ARM': 'ARM',  'SMCI': 'SMCI',
    'CRWD': 'CRWD', 'SNOW': 'SNOW', 'CRM': 'CRM',  'PANW': 'PANW',
    'UBER': 'UBER', 'ABNB': 'ABNB', 'NET': 'NET',  'DDOG': 'DDOG',
    'MRVL': 'MRVL', 'QCOM': 'QCOM', 'INTC': 'INTC','ON': 'ON',
}

# CRYPTO 확장 풀 (운용 4종목 + 후보 12종목 = 16종목)
CRYPTO_SCAN_POOL: dict[str, str] = {
    # 운용 중 4종목
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD', 'XRP': 'XRP-USD',
    # 후보 12종목
    'DOGE': 'DOGE-USD', 'ADA': 'ADA-USD',  'AVAX': 'AVAX-USD', 'LINK': 'LINK-USD',
    'DOT':  'DOT-USD',  'MATIC':'MATIC-USD','UNI':  'UNI-USD',  'ATOM': 'ATOM-USD',
    'LTC':  'LTC-USD',  'BCH':  'BCH-USD',  'NEAR': 'NEAR-USD', 'FIL':  'FIL-USD',
}

# ── 이미 운용 중인 종목 코드 세트 ────────────────────────────────────────────
ACTIVE_KR  = {'017670','035720','021240','005380','010140','086790','034020',
               '272210','000660','058470','064350','128940','012450','005930','009150','008060'}
ACTIVE_US  = {'AMD','MU','NVDA','AVGO','MSTR','LRCX','AMZN','SHOP','GOOGL','TSLA'}
ACTIVE_CRYPTO = {'BTC','ETH','SOL','XRP'}


# ── 공통 유틸 ────────────────────────────────────────────────────────────────

def _send_telegram(text: str) -> None:
    token   = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        print("  [Telegram] 미설정")
        return
    try:
        import requests
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        if r.status_code == 200:
            print('  [Telegram] 발송 완료')
        else:
            print(f'  [Telegram] 실패 {r.status_code}')
    except Exception as e:
        print(f'  [Telegram] 오류: {e}')


def _load_daily(yf_ticker: str) -> Optional[pd.DataFrame]:
    """일봉 데이터 로드 (yfinance v8 API)"""
    import urllib.request
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}'
           f'?interval=1d&range=2y')
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        result = data['chart']['result'][0]
        ts     = result['timestamp']
        ohlcv  = result['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open':   ohlcv['open'],
            'High':   ohlcv['high'],
            'Low':    ohlcv['low'],
            'Close':  ohlcv['close'],
            'Volume': ohlcv['volume'],
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert('Asia/Seoul'))
        return df.dropna(subset=['Close'])
    except Exception:
        return None


def _load_4h(yf_ticker: str) -> Optional[pd.DataFrame]:
    """4H 데이터 로드"""
    import urllib.request
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}'
           f'?interval=60m&range=6mo')
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        result = data['chart']['result'][0]
        ts     = result['timestamp']
        ohlcv  = result['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open':   ohlcv['open'],
            'High':   ohlcv['high'],
            'Low':    ohlcv['low'],
            'Close':  ohlcv['close'],
            'Volume': ohlcv['volume'],
        }, index=pd.to_datetime(ts, unit='s', utc=True))
        df = df.dropna(subset=['Close'])
        # 1H → 4H 리샘플
        df = df.resample('4h').agg({
            'Open': 'first', 'High': 'max',
            'Low': 'min', 'Close': 'last', 'Volume': 'sum',
        }).dropna()
        return df
    except Exception:
        return None


# ── 공통 기술지표 계산 ────────────────────────────────────────────────────────

def _calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """EMA200, RSI14, BB(2σ), ATR14, 모멘텀20 계산"""
    c = df['Close'].copy()

    df['ema200'] = c.ewm(span=200, adjust=False).mean()
    df['ema20']  = c.ewm(span=20,  adjust=False).mean()

    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi'] = 100 - 100 / (1 + gain / loss.replace(0, float('nan')))

    std2 = c.rolling(20).std()
    df['bb_upper'] = df['ema20'] + 2 * std2
    df['bb_lower'] = df['ema20'] - 2 * std2

    hl = df['High'] - df['Low']
    hc = (df['High'] - c.shift()).abs()
    lc = (df['Low']  - c.shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    df['mom20'] = c.pct_change(20) * 100

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    df['macd']   = macd
    df['signal_line'] = macd.ewm(span=9, adjust=False).mean()

    return df


# ── 신호 감지 (확장 스캐너용 범용) ──────────────────────────────────────────

def _score_candidate(df: pd.DataFrame, market: str) -> Optional[dict]:
    """
    종목 하나에 대해 다중 전략 점수화.
    신호 강도(quality_score) + 전략 힌트 반환.
    조건 미달 시 None.
    """
    if len(df) < 220:
        return None

    df = _calc_indicators(df.copy())
    last  = df.iloc[-1]
    prev  = df.iloc[-2]

    cl      = float(last['Close'])
    ema200  = float(last['ema200'])
    ema20   = float(last['ema20'])
    rsi     = float(last['rsi'])
    bb_lo   = float(last['bb_lower'])
    bb_up   = float(last['bb_upper'])
    atr     = float(last['atr'])
    mom20   = float(last['mom20'])
    macd    = float(last['macd'])
    sig_ln  = float(last['signal_line'])
    macd_p  = float(prev['macd'])
    sigl_p  = float(prev['signal_line'])
    vol     = float(last['Volume'])
    vol_avg = float(df['Volume'].iloc[-21:-1].mean()) if len(df) > 21 else 0

    if any(pd.isna(v) for v in [ema200, rsi, bb_lo, atr]):
        return None

    score      = 0
    tags: list[str] = []
    strategies: list[str] = []

    # ── 장기추세 필터 ──
    above_ema200 = cl > ema200
    if above_ema200:
        score += 1
        tags.append('EMA200')

    # ── BB 반등 신호 ──
    bb_reversal = cl <= bb_lo * 1.015 and rsi < 40 and above_ema200
    if bb_reversal:
        score += 3
        tags.append(f'BB반등(RSI{rsi:.0f})')
        strategies.append('BB반등')

    # ── MACD 골든크로스 ──
    macd_cross = macd > sig_ln and macd_p <= sigl_p and above_ema200
    if macd_cross:
        score += 3
        tags.append('MACD_X')
        strategies.append('MACD')

    # ── BB+모멘텀 ──
    bb_mom = (cl <= bb_lo * 1.01 and rsi < 40 and mom20 > 0 and above_ema200)
    if bb_mom:
        score += 2
        tags.append(f'BB_MOM(mom{mom20:.1f}%)')
        strategies.append('BB_MOM')

    # ── 거래량 급증 ──
    if vol_avg > 0 and vol > vol_avg * 1.5:
        score += 1
        tags.append('VolSpike')

    # ── RSI 과매도 회복 ──
    prev_rsi = float(prev['rsi'])
    if not pd.isna(prev_rsi) and prev_rsi < 30 and rsi >= 30:
        score += 2
        tags.append('RSI_Recovery')
        if 'BB반등' not in strategies:
            strategies.append('BB반등')

    # ── 모멘텀 강도 ──
    if mom20 > 10:
        score += 1
        tags.append(f'Mom+{mom20:.0f}%')

    # 최소 점수 2점 미만 제외
    if score < 2:
        return None

    # SL/TP 계산 (ATR 기반)
    sl_pct = max(float(atr) / cl, 0.015)
    sl_pct = min(sl_pct, 0.08)
    rr = 3.0 if market == 'CRYPTO' else 2.0
    tp_pct = sl_pct * rr

    return {
        'score':      score,
        'strategies': ', '.join(strategies) if strategies else 'BB반등',
        'tags':       ', '.join(tags),
        'price':      round(cl, 4),
        'sl_pct':     round(-sl_pct * 100, 2),
        'tp_pct':     round(tp_pct * 100, 2),
        'rsi':        round(rsi, 1),
        'ema200':     round(ema200, 2),
        'bb_lower':   round(bb_lo, 4),
        'mom20':      round(mom20, 2),
    }


# ── 시장별 스캔 ──────────────────────────────────────────────────────────────

def scan_kr() -> list[dict]:
    print('\n[KR 확장 스캔] 40종목 분석 중...')
    candidates = []
    for code, (name, yf_tk) in KR_SCAN_POOL.items():
        df = _load_daily(yf_tk)
        if df is None:
            continue
        result = _score_candidate(df, 'KR')
        if result is None:
            continue
        result.update({
            'ticker': code,
            'name':   name,
            'market': 'KR',
            'in_universe': code in ACTIVE_KR,
        })
        candidates.append(result)
        status = '★운용중' if code in ACTIVE_KR else '후보'
        print(f'  [{status}] {name}({code}) | 점수={result["score"]} | '
              f'전략={result["strategies"]} | RSI={result["rsi"]} | {result["tags"]}')

    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_N]


def scan_us() -> list[dict]:
    print('\n[US 확장 스캔] 30종목 분석 중...')
    candidates = []
    for code, yf_tk in US_SCAN_POOL.items():
        df = _load_daily(yf_tk)
        if df is None:
            continue
        result = _score_candidate(df, 'US')
        if result is None:
            continue
        result.update({
            'ticker': code,
            'name':   code,
            'market': 'US',
            'in_universe': code in ACTIVE_US,
        })
        candidates.append(result)
        status = '★운용중' if code in ACTIVE_US else '후보'
        print(f'  [{status}] {code} | 점수={result["score"]} | '
              f'전략={result["strategies"]} | RSI={result["rsi"]} | {result["tags"]}')

    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_N]


def scan_crypto() -> list[dict]:
    print('\n[CRYPTO 확장 스캔] 16종목 4H 분석 중...')
    candidates = []
    for code, yf_tk in CRYPTO_SCAN_POOL.items():
        df = _load_4h(yf_tk)
        if df is None:
            continue
        result = _score_candidate(df, 'CRYPTO')
        if result is None:
            continue
        result.update({
            'ticker': code,
            'name':   code,
            'market': 'CRYPTO',
            'in_universe': code in ACTIVE_CRYPTO,
        })
        candidates.append(result)
        status = '★운용중' if code in ACTIVE_CRYPTO else '후보'
        print(f'  [{status}] {code} | 점수={result["score"]} | '
              f'전략={result["strategies"]} | RSI={result["rsi"]} | {result["tags"]}')

    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_N]


# ── 결과 저장 & 알림 ─────────────────────────────────────────────────────────

def _build_telegram_msg(results: dict[str, list[dict]]) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f'<b>[Warren] 일일 종목 서칭 — {now}</b>', '']

    market_emoji = {'KR': '🇰🇷', 'US': '🇺🇸', 'CRYPTO': '🪙'}

    for market, candidates in results.items():
        emoji = market_emoji.get(market, '')
        lines.append(f'{emoji} <b>{market} TOP {TOP_N}</b>')
        if not candidates:
            lines.append('  신호 없음')
        else:
            for i, c in enumerate(candidates, 1):
                star   = '★' if c['in_universe'] else '◆신규'
                name   = c.get('name', c['ticker'])
                ticker = c['ticker']
                lines.append(
                    f'  {i}. {star} {name}({ticker}) '
                    f'| Q={c["score"]} | {c["strategies"]} '
                    f'| SL{c["sl_pct"]}% TP+{c["tp_pct"]}% '
                    f'| RSI={c["rsi"]}'
                )
        lines.append('')

    lines.append('★=현재 운용중  ◆=신규 편입 후보')
    return '\n'.join(lines)


def _save_result(results: dict[str, list[dict]]) -> Path:
    today = datetime.now().strftime('%Y-%m-%d')
    path  = SCAN_DIR / f'{today}.json'
    payload = {
        'date':    today,
        'scan_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'results': results,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'\n  [저장] {path}')
    return path


def _print_summary(results: dict[str, list[dict]]) -> None:
    print('\n' + '=' * 60)
    print(f'  Warren Daily Scanner — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 60)
    for market, candidates in results.items():
        print(f'\n  [{market}] TOP {TOP_N}')
        if not candidates:
            print('    신호 없음')
            continue
        for i, c in enumerate(candidates, 1):
            star   = '★운용중' if c['in_universe'] else '◆신규후보'
            name   = c.get('name', c['ticker'])
            print(f'    {i}. [{star}] {name}({c["ticker"]}) '
                  f'Q={c["score"]} | {c["strategies"]} | '
                  f'SL{c["sl_pct"]}% / TP+{c["tp_pct"]}% | '
                  f'RSI={c["rsi"]} | {c["tags"]}')


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description='Warren Daily Market Scanner')
    parser.add_argument('--market', choices=['KR', 'US', 'CRYPTO'],
                        help='특정 시장만 스캔 (기본: 전체)')
    args = parser.parse_args()

    results: dict[str, list[dict]] = {}

    if args.market in (None, 'KR'):
        results['KR'] = scan_kr()
    if args.market in (None, 'US'):
        results['US'] = scan_us()
    if args.market in (None, 'CRYPTO'):
        results['CRYPTO'] = scan_crypto()

    _print_summary(results)
    _save_result(results)

    msg = _build_telegram_msg(results)
    _send_telegram(msg)


if __name__ == '__main__':
    main()
