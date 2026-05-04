# -*- coding: utf-8 -*-
"""
유니버스 백테스트 — 완화 조건 버전 (V4_RELAXED)
=================================================
조정 근거 및 기록 (2026-04-28):
  - 목적: 포워드테스팅 케이스 축적. 기존 조건(BB1하단+RSI<60)이 너무 타이트해
          신호가 거의 발생하지 않아 실질적인 테스트가 불가능한 상태.
  - 변경 내용 (잠정, 테스트 목적):
      1. BB 기준: BB1 하단(MA20-1σ) → MA20 중심선 이하 (완화)
      2. RSI 임계: RSI < 60 → RSI < 70 (완화)
      3. 품질 점수: 4점↑ → 3점↑ (완화)
  - 핵심 원칙 유지:
      - FVG 또는 OB 존 필수
      - EMA200 위 (추세 방향)
      - R:R 1:2 (KR/US), 1:3 (CRYPTO)
  - 신규 후보 추가:
      US: HESAY(에르메스), ISRG(인튜이티브서지컬), RTX, MP(MP머티리얼즈), QQQI, TEST
      JP: 3110.T(닛토방적), 5016.T(JX어드밴스드메탈스)
  - 이 파일 결과는 조건별 A/B 비교 데이터로만 활용.
    실전 전략 변경은 별도 승인 후 적용.
"""
import warnings; warnings.filterwarnings('ignore')
import sys, json
import pandas as pd
import numpy as np
import urllib.request
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ── 완화 조건 파라미터 ─────────────────────────────────────────
RSI_THRESHOLD  = 70      # 완화: 60 → 70
USE_BB1_LOWER  = False   # 완화: BB1하단 대신 MA20 중심선 사용
MIN_QUALITY    = 3       # 완화: 4 → 3
RR_RATIO_SWING = 2.0
SL_FLOOR       = 0.02
SL_CAP         = 0.08
MAX_HOLD_DAYS  = 15
FEE            = 0.0023  # KR 수수료

# ── 신규 후보 유니버스 ─────────────────────────────────────────
NEW_US_CANDIDATES = {
    'HESAY': '에르메스ADR',
    'ISRG':  '인튜이티브서지컬',
    'RTX':   'RTX',
    'MP':    'MP머티리얼즈',
    'QQQI':  'QQQI',
    'TEST':  'TEST',
}

NEW_JP_CANDIDATES = {
    '3110.T': '닛토방적',
    '5016.T': 'JX어드밴스드메탈스',
}

# 기존 KR/US도 완화 조건으로 재테스트
EXISTING_KR = {
    '105560.KS': 'KB금융',
    '005380.KS': '현대차',
    '000270.KS': '기아',
    '005930.KS': '삼성전자',
    '008060.KS': '대덕전자',
    '009150.KS': '삼성전기',
    '000660.KS': 'SK하이닉스',
    '034020.KS': '두산에너빌리티',
    '051910.KS': 'LG화학',
    '035420.KS': 'NAVER',
}

EXISTING_US = {
    'GOOGL': '구글',
    'SOXX':  '반도체ETF',
    'MSFT':  'MSFT',
    'META':  'META',
    'AMZN':  '아마존',
    'NVDA':  '엔비디아',
    'TSLA':  '테슬라',
    'PLTR':  '팔란티어',
}


def _fetch(ticker: str, range_str: str = '5y') -> pd.DataFrame | None:
    """Yahoo Finance v8 API 직접 호출"""
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval=1d&range={range_str}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        r = data.get('chart', {}).get('result', [])
        if not r:
            return None
        ts  = r[0].get('timestamp', [])
        q   = r[0].get('indicators', {}).get('quote', [{}])[0]
        adj = r[0].get('indicators', {}).get('adjclose', [])
        closes = (adj[0]['adjclose'] if adj and isinstance(adj[0], dict) and adj[0].get('adjclose')
                  else q.get('close', []))
        df = pd.DataFrame({
            'Open':   q.get('open', []),
            'High':   q.get('high', []),
            'Low':    q.get('low',  []),
            'Close':  closes,
            'Volume': q.get('volume', []),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df.dropna()
    except Exception:
        return None


def _indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df['Close']
    df['ema200'] = c.ewm(span=200, adjust=False).mean()
    ma20         = c.rolling(20).mean()
    sd20         = c.rolling(20).std()
    df['ma20']   = ma20
    df['bb1_lo'] = ma20 - sd20
    # RSI
    d = c.diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df['rsi'] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    # FVG
    df['fvg_bull'] = (df['Low'].shift(-1) > df['High'].shift(1)) & (c > c.shift(1))
    # OB (하락 후 급등 전 마지막 하락봉)
    df['ob_bull']  = (c.shift(1) < c.shift(2)) & (c > c.shift(1)) & (c > ma20)
    return df


def _backtest(ticker: str, name: str, df: pd.DataFrame,
              rr: float = 2.0, fee: float = FEE) -> dict:
    """완화 조건 스윙 백테스트"""
    df = _indicators(df)
    trades = []

    i = 200
    while i < len(df) - 1:
        row = df.iloc[i]
        # ── 진입 조건 (완화) ───────────────────────────────
        if row['Close'] <= row['ema200']:
            i += 1; continue
        # BB 조건: 완화 → MA20 이하
        bb_ok = row['Close'] < row['ma20'] if not USE_BB1_LOWER else row['Close'] < row['bb1_lo']
        if not bb_ok:
            i += 1; continue
        # RSI 완화
        if row['rsi'] > RSI_THRESHOLD or pd.isna(row['rsi']):
            i += 1; continue
        # FVG or OB
        if not (row['fvg_bull'] or row['ob_bull']):
            i += 1; continue

        entry = row['Close']
        sl    = max(row['Low'] * (1 - 0.005), entry * (1 - SL_CAP))
        sl    = min(sl, entry * (1 - SL_FLOOR))
        sl_pct = (entry - sl) / entry
        tp    = entry + sl_pct * entry * rr

        # 보유 기간 탐색
        result = 'HOLD'
        exit_price = None
        for j in range(1, MAX_HOLD_DAYS + 1):
            if i + j >= len(df):
                break
            future = df.iloc[i + j]
            if future['Low'] <= sl:
                result = 'SL'; exit_price = sl; break
            if future['High'] >= tp:
                result = 'TP'; exit_price = tp; break
        if result == 'HOLD':
            exit_price = df.iloc[min(i + MAX_HOLD_DAYS, len(df)-1)]['Close']
            result = 'TP' if exit_price >= entry else 'SL'

        pnl_pct = (exit_price - entry) / entry - fee
        trades.append({'result': result, 'pnl': pnl_pct, 'entry_idx': i})
        i += MAX_HOLD_DAYS  # 홀드 후 다음 탐색

    if not trades:
        return {'ticker': ticker, 'name': name, 'signals': 0,
                'wr': 0, 'ev': 0, 'mdd': 0, 'score': 0}

    n     = len(trades)
    wins  = sum(1 for t in trades if t['result'] == 'TP')
    wr    = wins / n * 100
    ev    = np.mean([t['pnl'] for t in trades]) * 100
    # MDD
    eq = [1.0]
    for t in trades:
        eq.append(eq[-1] * (1 + t['pnl']))
    eq_s = pd.Series(eq)
    mdd  = ((eq_s.cummax() - eq_s) / eq_s.cummax()).max() * 100
    score = ev * 20 + wr * 0.4 - mdd * 0.5

    return {
        'ticker':  ticker,
        'name':    name,
        'signals': n,
        'wr':      round(wr, 1),
        'ev':      round(ev, 3),
        'mdd':     round(mdd, 1),
        'score':   round(score, 2),
    }


def run_group(label: str, tickers: dict, rr: float = 2.0,
              fee: float = FEE, range_str: str = '5y') -> list:
    print(f'\n{"="*60}')
    print(f'  {label}  [완화조건: RSI<{RSI_THRESHOLD}, MA20이하, 품질3점↑]')
    print(f'{"="*60}')
    results = []
    for ticker, name in tickers.items():
        df = _fetch(ticker, range_str)
        if df is None or len(df) < 250:
            print(f'  {name:18s} ({ticker}) — 데이터 부족')
            continue
        r = _backtest(ticker, name, df, rr=rr, fee=fee)
        results.append(r)
        flag = '★' if r['score'] > 5 else ' '
        print(f'  {flag}{name:18s} | 신호={r["signals"]:3d}건 | '
              f'WR={r["wr"]:5.1f}% | EV={r["ev"]:+.3f}% | '
              f'MDD={r["mdd"]:5.1f}% | Score={r["score"]:6.2f}')
    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def main():
    print(f'\n{"="*60}')
    print(f'  유니버스 백테스트 V4_RELAXED  [{datetime.now():%Y-%m-%d %H:%M}]')
    print(f'  목적: 포워드테스팅 케이스 축적용 — 잠정 완화 조건')
    print(f'  조정: BB→MA20이하 / RSI<70 / 품질3점↑')
    print(f'{"="*60}')

    all_results = {}

    # 1. 기존 KR (완화 재테스트)
    kr = run_group('KR 기존 종목 — 완화 재테스트', EXISTING_KR, rr=2.0, fee=0.0023)
    all_results['KR_existing'] = kr

    # 2. 기존 US (완화 재테스트)
    us = run_group('US 기존 종목 — 완화 재테스트', EXISTING_US, rr=2.0, fee=0.005)
    all_results['US_existing'] = us

    # 3. US 신규 후보
    us_new = run_group('US 신규 후보', NEW_US_CANDIDATES, rr=2.0, fee=0.005)
    all_results['US_new'] = us_new

    # 4. JP 신규 후보
    jp = run_group('JP 신규 후보 (닛토방적/JX메탈스)', NEW_JP_CANDIDATES, rr=2.0, fee=0.0030)
    all_results['JP_new'] = jp

    # ── 통합 랭킹 ──────────────────────────────────────────
    print(f'\n{"="*60}')
    print(f'  통합 TOP 15 (Score 기준)')
    print(f'{"="*60}')
    flat = []
    for group, items in all_results.items():
        for r in items:
            r['group'] = group
            flat.append(r)
    flat.sort(key=lambda x: x['score'], reverse=True)
    for i, r in enumerate(flat[:15], 1):
        print(f'  {i:2d}. [{r["group"]:12s}] {r["name"]:18s} '
              f'WR={r["wr"]:5.1f}% EV={r["ev"]:+.3f}% Score={r["score"]:6.2f}')

    # ── CSV 저장 ────────────────────────────────────────────
    out_path = LOG_DIR / 'universe_bt_relaxed.csv'
    rows = []
    for group, items in all_results.items():
        for r in items:
            rows.append({**r, 'group': group,
                         'condition': f'RSI<{RSI_THRESHOLD}_MA20_Q{MIN_QUALITY}',
                         'run_at': datetime.now().strftime('%Y-%m-%d %H:%M')})
    pd.DataFrame(rows).to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\n  결과 저장: {out_path.name}')
    print(f'\n  [조정 근거] RSI<70 + MA20이하 완화 — 케이스 축적 목적 (잠정)')
    print(f'  [원칙 유지] FVG/OB + EMA200 필터 유지')
    print(f'  [다음 단계] 완화조건 케이스 30건↑ 쌓인 후 원본 조건과 WR 비교')


if __name__ == '__main__':
    main()
