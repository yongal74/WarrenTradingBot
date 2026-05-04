# -*- coding: utf-8 -*-
"""
paper_base.py — 공통 Paper Trading 엔진
=========================================
V1 / V2 / V3 모두 이 모듈을 임포트해서 사용.
전략 로직(detect_signal)만 각 버전 파일에 정의.

책임:
  - 일봉 데이터 로드 (yfinance)
  - 포트폴리오 상태 JSON 영속화
  - 거래 로그 CSV (중복 방지)
  - 포지션 SL/TP/MAX_HOLD 체크
  - 요약 출력

사용 방법:
  from paper_base import run_loop
  run_loop(VERSION, CONFIG, UNIVERSE, detect_signal)
"""
import sys, time, warnings, json, csv, os, requests
warnings.filterwarnings('ignore')
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable

# ── SSL 인증서 경로 고정 (Windows + curl_cffi 호환) ──────────────
try:
    import certifi
    _ca = certifi.where()
    os.environ.setdefault('SSL_CERT_FILE',       _ca)
    os.environ.setdefault('REQUESTS_CA_BUNDLE',  _ca)
    os.environ.setdefault('CURL_CA_BUNDLE',      _ca)  # curl_cffi용
except Exception:
    pass

# SSL 비검증 세션 — curl_cffi 우선, 없으면 requests fallback
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _make_session():
    """yfinance에 전달할 SSL 비검증 세션. curl_cffi 우선."""
    try:
        from curl_cffi import requests as _cr
        return _cr.Session(verify=False)
    except Exception:
        s = requests.Session()
        s.verify = False
        return s

import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 텔레그램 알림 ─────────────────────────────────────────────
_TG_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
_TG_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
_TG_ENABLED = bool(_TG_TOKEN and _TG_CHAT_ID)
_tg_cooldown: dict = {}   # {msg_key: last_sent_ts} — 동일 메시지 도배 방지


def _tg_send(text: str, key: str = '', cooldown_min: int = 0) -> None:
    """
    텔레그램 메시지 발송.
    key + cooldown_min 으로 동일 알림 중복 발송 차단.
    """
    if not _TG_ENABLED:
        return
    if key and cooldown_min:
        last = _tg_cooldown.get(key, 0)
        if (time.time() - last) < cooldown_min * 60:
            return
        _tg_cooldown[key] = time.time()
    try:
        requests.post(
            f'https://api.telegram.org/bot{_TG_TOKEN}/sendMessage',
            json={'chat_id': _TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
    except Exception:
        pass


def notify_entry(version: str, pos: dict) -> None:
    """신규 진입 알림 — 핵심 정보만."""
    entry  = pos['entry']
    sl     = pos['sl']
    tp     = pos['tp']
    rr     = round((tp - entry) / (entry - sl), 1) if entry > sl else 0
    sl_pct = pos.get('sl_pct', round((entry - sl) / entry * 100, 1))
    tp_pct = round((tp - entry) / entry * 100, 1)
    size_m = pos['size_krw'] / 1e4

    msg = (
        f"<b>[{version.upper()}] 신규 진입</b>\n"
        f"종목: <b>{pos.get('name', pos['ticker'])}</b> ({pos['ticker']})\n"
        f"전략: <code>{pos['signal_type']}</code> | {pos['market']}\n"
        f"──────────────────\n"
        f"진입가:  <b>{entry:,.4f}</b>\n"
        f"손절가:  {sl:,.4f}  ({sl_pct:.1f}%)\n"
        f"목표가:  {tp:,.4f}  (+{tp_pct:.1f}%)\n"
        f"R:R:     1 : {rr}\n"
        f"포지션:  {size_m:.0f}만원\n"
        f"최대손실: -{pos['size_krw'] * float(sl_pct) / 100 / 1e4:.1f}만원"
    )
    _tg_send(msg, key=f"entry_{version}_{pos['ticker']}_{pos['open_time']}")


def notify_close(version: str, trade: dict) -> None:
    """청산 알림 — 결과 중심."""
    pnl    = trade['pnl_krw']
    pnl_p  = trade['pnl_pct']
    sign   = '+' if pnl >= 0 else ''
    result = 'WIN' if pnl > 0 else 'LOSS'
    emoji  = '' if pnl > 0 else ''

    msg = (
        f"<b>{emoji} [{version.upper()}] {result} — {trade['close_reason']}</b>\n"
        f"종목: <b>{trade.get('name', trade['ticker'])}</b> ({trade['ticker']})\n"
        f"──────────────────\n"
        f"진입: {trade['entry']:,.4f}  →  청산: {trade['exit']:,.4f}\n"
        f"손익: <b>{sign}{pnl:,.0f}원</b>  ({sign}{pnl_p:.2f}%)\n"
        f"보유: {trade.get('hold_days', '?')}일"
    )
    _tg_send(msg, key=f"close_{version}_{trade['ticker']}_{trade['open_time']}")


def notify_daily_summary(version: str, pf: dict, positions: list) -> None:
    """하루 1회 포트폴리오 요약 알림."""
    t_init = sum(pf.get('initial', {}).values())
    t_now  = sum(pf.get('capital', {}).values()) + sum(
        p['size_krw'] for p in positions)
    t_pnl  = sum(pf.get('realized', {}).values())
    w, l   = pf.get('wins', 0), pf.get('losses', 0)
    total  = w + l
    wr     = w / total * 100 if total else 0
    ret    = (t_now - t_init) / t_init * 100 if t_init else 0

    mkt_lines = []
    for mkt in ('KR', 'US', 'CRYPTO'):
        init = pf.get('initial', {}).get(mkt, 0)
        now  = pf.get('capital', {}).get(mkt, 0)
        pnl  = pf.get('realized', {}).get(mkt, 0)
        if init:
            mkt_lines.append(
                f"  {mkt:6s}: {now/1e4:.0f}만  ({(now-init)/init*100:+.1f}%)"
                f"  실현 {pnl:+,.0f}원"
            )

    msg = (
        f"<b>[{version.upper()}] 일일 요약</b>  {datetime.now().strftime('%m/%d %H:%M')}\n"
        f"──────────────────\n"
        f"총자산:  <b>{t_now/1e4:.1f}만원</b>  ({ret:+.1f}%)\n"
        f"실현손익: <b>{t_pnl:+,.0f}원</b>\n"
        f"승률:    {wr:.1f}%  ({w}승 {l}패, {total}건)\n"
        f"오픈:    {len(positions)}개\n"
        f"{''.join(chr(10)+l for l in mkt_lines)}"
    )
    _tg_send(msg, key=f"daily_{version}", cooldown_min=12 * 60)  # 12시간 쿨다운

LOGS = Path(__file__).parent / 'logs'
LOGS.mkdir(exist_ok=True)

# ── 데이터 로드 (market 별 라우팅) ───────────────────────────
def fetch_daily(data_key: str, market: str = 'US') -> pd.DataFrame | None:
    """
    일봉 OHLCV 반환. 최소 55봉 미만이면 None.
    market='KR'     → KIS API  (data_key = 종목코드, e.g. '005930')
    market='CRYPTO' → Upbit API (data_key = 'KRW-BTC' 등)
    market='US'     → yfinance  (data_key = 'AAPL' 등)
    """
    try:
        if market == 'KR':
            from core.kis_trader import get_daily_df
            df = get_daily_df(data_key, count=200)
        elif market == 'CRYPTO':
            from core.upbit_data import get_daily_df
            df = get_daily_df(data_key, count=200)
        else:  # US
            df = yf.download(data_key, period='1y', interval='1d',
                             auto_adjust=True, progress=False,
                             multi_level_index=False, session=_make_session())
            if df is not None and not df.empty:
                if df.index.tz:
                    df.index = df.index.tz_localize(None)
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

        if df is None or df.empty:
            return None
        return df if len(df) >= 55 else None
    except Exception:
        return None


def fetch_realtime_price(data_key: str, market: str = 'US') -> float | None:
    """
    현재가 반환.
    market='KR'     → KIS API get_price()
    market='CRYPTO' → Upbit API get_current_price()
    market='US'     → yfinance
    """
    try:
        if market == 'KR':
            from core.kis_trader import get_price
            p = get_price(data_key)
            return float(p) if p else None
        elif market == 'CRYPTO':
            from core.upbit_data import get_current_price
            return get_current_price(data_key)
        else:  # US
            df = yf.download(data_key, period='2d', interval='1d',
                             auto_adjust=True, progress=False,
                             multi_level_index=False, session=_make_session())
            if df is not None and not df.empty:
                return float(df['Close'].iloc[-1])
    except Exception:
        pass
    return None


# ── 포트폴리오 I/O ────────────────────────────────────────────
def _pf_file(version: str) -> Path:
    return LOGS / f'{version.lower()}_portfolio.json'

def _pos_file(version: str) -> Path:
    return LOGS / f'{version.lower()}_positions.json'

def _trades_file(version: str) -> Path:
    return LOGS / f'{version.lower()}_trades.csv'


def load_portfolio(version: str, initial: dict) -> dict:
    f = _pf_file(version)
    if f.exists():
        try:
            return json.loads(f.read_text('utf-8'))
        except Exception:
            pass
    return {
        'version':  version,
        'start':    datetime.now().strftime('%Y-%m-%d %H:%M'),
        'capital':  dict(initial),
        'initial':  dict(initial),
        'realized': {m: 0.0 for m in initial},
        'wins':     0,
        'losses':   0,
        'used_zones': {},   # {ticker: [zone_key, ...]} — B1 재진입 차단
    }

def save_portfolio(version: str, pf: dict) -> None:
    _pf_file(version).write_text(
        json.dumps(pf, ensure_ascii=False, indent=2), 'utf-8')


def load_positions(version: str) -> list:
    f = _pos_file(version)
    if f.exists():
        try:
            return json.loads(f.read_text('utf-8')).get('positions', [])
        except Exception:
            pass
    return []

def save_positions(version: str, positions: list) -> None:
    _pos_file(version).write_text(
        json.dumps({'positions': positions,
                    'saved_at': datetime.now().isoformat()},
                   ensure_ascii=False, indent=2), 'utf-8')


# ── 거래 로깅 — B2: 중복 방지 ────────────────────────────────
_logged_keys: set = set()

def log_trade(version: str, trade: dict) -> None:
    """open_time+ticker 기준 중복 로깅 차단."""
    key = f"{trade['open_time']}|{trade['ticker']}"
    if key in _logged_keys:
        return
    _logged_keys.add(key)

    tf = _trades_file(version)
    need_hdr = not tf.exists()
    with open(tf, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=trade.keys())
        if need_hdr:
            w.writeheader()
        w.writerow(trade)


# ── 포지션 청산 체크 ──────────────────────────────────────────
def check_positions(version: str,
                    positions: list,
                    pf: dict,
                    max_hold_days: int = 20) -> list:
    """
    보유 포지션별 SL / TP / MAX_HOLD 체크.
    청산 시 capital 및 realized_pnl 정확 반영 (B3).
    """
    remaining = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for pos in positions:
        ticker, market = pos['ticker'], pos['market']
        size  = float(pos['size_krw'])   # B3: open 시 기록한 값 그대로
        entry = float(pos['entry'])
        sl    = float(pos['sl'])
        tp    = float(pos['tp'])

        cur = fetch_realtime_price(pos['yf_ticker'], pos.get('market', 'US'))
        if cur is None:
            remaining.append(pos)
            continue

        open_dt  = datetime.fromisoformat(pos['open_time'])
        hold_day = (datetime.now() - open_dt).days
        reason   = None
        exit_p   = cur

        if cur <= sl:
            reason, exit_p = 'SL', sl
        elif cur >= tp:
            reason, exit_p = 'TP', tp
        elif hold_day >= max_hold_days:
            reason, exit_p = 'MAX_HOLD', cur

        if reason:
            pnl_pct = (exit_p - entry) / entry * 100
            pnl_krw = size * pnl_pct / 100

            # B3: capital 정확 복원
            pf['capital'][market]  = pf['capital'].get(market, 0.0) + size + pnl_krw
            pf['realized'][market] = pf['realized'].get(market, 0.0) + pnl_krw
            key = 'wins' if pnl_pct > 0 else 'losses'
            pf[key] = pf.get(key, 0) + 1

            trade = {
                'open_time':  pos['open_time'],
                'close_time': now_str,
                'version':    version,
                'ticker':     ticker,
                'name':       pos.get('name', ticker),
                'market':     market,
                'signal':     pos.get('signal_type', ''),
                'entry':      round(entry, 6),
                'exit':       round(exit_p, 6),
                'sl':         round(sl, 6),
                'tp':         round(tp, 6),
                'size_krw':   round(size),
                'pnl_pct':    round(pnl_pct, 2),
                'pnl_krw':    round(pnl_krw),
                'result':     'WIN' if pnl_pct > 0 else 'LOSS',
                'reason':     reason,
                'hold_days':  hold_day,
            }
            log_trade(version, trade)
            notify_close(version, trade)
            sign = '+' if pnl_krw >= 0 else ''
            print(f"    [{reason:8s}] {pos.get('name', ticker):12s}"
                  f"  {sign}{pnl_krw:>10,.0f}원  ({sign}{pnl_pct:.2f}%)")
        else:
            pnl_now = (cur - entry) / entry * 100
            sign = '+' if pnl_now >= 0 else ''
            print(f"    [보유 {hold_day:2d}일] {pos.get('name', ticker):12s}"
                  f"  현재 {cur:>10,.4f}  ({sign}{pnl_now:.2f}%)")
            remaining.append(pos)

    return remaining


# ── 신규 진입 스캔 ────────────────────────────────────────────
def scan_entries(version: str,
                 pf: dict,
                 positions: list,
                 universe: dict,
                 config: dict,
                 detect_fn: Callable) -> list:
    """
    universe를 순회하며 detect_fn 호출.
    신호 있으면 포지션 생성.
    B1: zone_key 중복 차단.
    """
    new_positions = []
    open_tickers  = {p['ticker'] for p in positions}
    now_str       = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pos_sizes     = config['pos_size']
    max_pos       = config['max_pos']

    for market, assets in universe.items():
        avail    = pf['capital'].get(market, 0.0)
        pos_size = pos_sizes[market]
        mkt_cnt  = sum(1 for p in positions if p['market'] == market)

        for code, name, yf_tk in assets:
            if code in open_tickers:
                continue
            if mkt_cnt >= max_pos.get(market, 5):
                break
            if avail < pos_size:
                break

            df = fetch_daily(yf_tk, market)
            if df is None:
                print(f"    {name:12s}: 데이터없음")
                continue

            sig = detect_fn(df, code)
            if sig is None:
                print(f"    {name:12s}: 신호없음")
                continue

            # B1: 사용된 구간 제외
            used = pf.setdefault('used_zones', {}).setdefault(code, [])
            if sig.get('zone_key') in used:
                print(f"    {name:12s}: 신호있음 (기사용 구간)")
                continue

            # zone_key 기록 (최대 200개)
            used.append(sig['zone_key'])
            pf['used_zones'][code] = used[-200:]

            # B3: pos_size 일관 저장
            pf['capital'][market] = avail - pos_size
            avail = pf['capital'][market]
            mkt_cnt += 1

            pos = {
                'open_time':   now_str,
                'ticker':      code,
                'name':        name,
                'market':      market,
                'yf_ticker':   yf_tk,
                'signal_type': sig['type'],
                'zone_key':    sig.get('zone_key', ''),
                'entry':       sig['entry'],
                'sl':          sig['sl'],
                'tp':          sig['tp'],
                'sl_pct':      sig.get('sl_pct', 0),
                'size_krw':    pos_size,   # B3: 이 값이 close 시 반환됨
            }
            new_positions.append(pos)
            open_tickers.add(code)
            notify_entry(version, pos)
            print(f"    ★ [{sig['type']:15s}] {name:12s}"
                  f"  진입={sig['entry']:>10,.4f}"
                  f"  SL={sig['sl']:>10,.4f}  TP={sig['tp']:>10,.4f}")

    return new_positions


# ── 요약 출력 ────────────────────────────────────────────────
def print_summary(version: str, pf: dict, positions: list) -> None:
    t_init = sum(pf['initial'].values())
    t_now  = sum(pf['capital'].values()) + sum(
        p['size_krw'] for p in positions)   # 오픈 포지션 포함
    t_pnl  = sum(pf['realized'].values())
    w, l   = pf.get('wins', 0), pf.get('losses', 0)
    total  = w + l
    wr     = w / total * 100 if total else 0

    pos_gains  = sum(r for r in pf['realized'].values() if r > 0)
    pos_losses = abs(sum(r for r in pf['realized'].values() if r < 0))
    pf_val     = pos_gains / pos_losses if pos_losses > 0 else float('inf')

    ret = (t_now - t_init) / t_init * 100 if t_init > 0 else 0

    print(f"\n  [{version}] "
          f"총자산 {t_now/1e4:>7.1f}만  ({ret:+.1f}%) | "
          f"실현손익 {t_pnl:>+10,.0f}원 | "
          f"거래 {total:>3d}건  WR {wr:>5.1f}%  PF {pf_val:>5.2f} | "
          f"오픈 {len(positions)}개")


# ── 메인 루프 ────────────────────────────────────────────────
def run_loop(version: str,
             config: dict,
             universe: dict,
             detect_fn: Callable) -> None:
    """
    스윙 페이퍼 트레이딩 루프.
    config 필수 키:
      initial     : {KR: int, US: int, CRYPTO: int}
      pos_size    : {KR: int, US: int, CRYPTO: int}
      max_pos     : {KR: int, US: int, CRYPTO: int}
      max_hold_days: int
      loop_sec    : int  (스캔 간격, 스윙은 4H = 14400 권장)
    """
    initial       = config['initial']
    loop_sec      = config.get('loop_sec', 4 * 3600)
    max_hold_days = config.get('max_hold_days', 20)

    print('=' * 70)
    print(f'  Warren Swing Paper Trading [{version}]')
    print(f'  자본: KR {initial["KR"]/1e4:.0f}만 | '
          f'US {initial["US"]/1e4:.0f}만 | CRYPTO {initial["CRYPTO"]/1e4:.0f}만')
    print(f'  포지션 크기: {config["pos_size"]}')
    print(f'  스캔 간격: {loop_sec//3600}시간  |  종료: Ctrl+C')
    print('=' * 70)

    while True:
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f'\n[{ts}] {version} 스캔')

            pf        = load_portfolio(version, initial)
            positions = load_positions(version)

            print(f'\n  포지션 점검 ({len(positions)}개):')
            if positions:
                positions = check_positions(version, positions, pf, max_hold_days)
            else:
                print('    없음')

            print(f'\n  신호 스캔:')
            new_pos = scan_entries(version, pf, positions, universe, config, detect_fn)
            positions.extend(new_pos)

            save_portfolio(version, pf)
            save_positions(version, positions)
            print_summary(version, pf, positions)
            notify_daily_summary(version, pf, positions)

            print(f'  다음 스캔: {loop_sec//3600}시간 후')
            time.sleep(loop_sec)

        except KeyboardInterrupt:
            print(f'\n  [{version}] 종료')
            break
        except Exception as e:
            print(f'  오류: {e}')
            time.sleep(300)
