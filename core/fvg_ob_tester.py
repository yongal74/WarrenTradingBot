# -*- coding: utf-8 -*-
"""
FVG + Order Block 포워드 테스터
백테스트와 동일한 로직으로 실시간 신호 감지
"""
import warnings; warnings.filterwarnings('ignore')
import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

# ── 파라미터 (백테스트와 동일) ────────────────────────────────
RR_RATIO    = 2.0
MAX_SL_PCT  = 0.015
MIN_SL_PCT  = 0.001
ZONE_EXPIRE = 20   # 봉 기준

# ── 진입 품질 필터 기준 ───────────────────────────────────
MIN_ENTRY_QUALITY = 3   # 7점 중 3점 이상만 신호 발생

KR_TICKERS = {
    '005930': ('삼성전자',       '005930.KS', '15m'),
    '000660': ('SK하이닉스',     '000660.KS', '15m'),
    '009150': ('삼성전기',       '009150.KS', '15m'),
    '034020': ('두산에너빌리티', '034020.KS', '15m'),
    '008060': ('대덕전자',       '008060.KS', '15m'),
}

US_TICKERS = {
    'NVDA': ('엔비디아',  'NVDA', '15m'),
    'PLTR': ('팔란티어',  'PLTR', '15m'),
    'AMD':  ('AMD',       'AMD',  '15m'),
    'TSLA': ('테슬라',    'TSLA', '15m'),
    'SOXX': ('반도체ETF', 'SOXX', '15m'),
}

CRYPTO_TICKERS = {
    'BTC': ('비트코인', 'BTC-USD', '15m'),
    'ETH': ('이더리움', 'ETH-USD', '15m'),
    'SOL': ('솔라나',   'SOL-USD', '15m'),
    'XRP': ('리플',     'XRP-USD', '15m'),
}


def _load(yf_ticker: str, interval: str = '15m') -> pd.DataFrame | None:
    try:
        df = yf.download(yf_ticker, period='5d', interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception as e:
        return None


def _detect_fvg(df: pd.DataFrame) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG', 'formed_i':i,
                          'zone_high':lo0, 'zone_low':hi2,
                          'expire_i':i + ZONE_EXPIRE})
    return zones


def _detect_ob(df: pd.DataFrame) -> list:
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB', 'formed_i':i,
                          'zone_high':float(b['High']),
                          'zone_low':float(b['Low']),
                          'expire_i':i + ZONE_EXPIRE})
    return zones


def _entry_quality_score(df: pd.DataFrame, entry: float, zone_low: float) -> tuple[int, list]:
    """
    진입 품질 7가지 기준으로 점수 계산 (0~7)
    점수가 높을수록 좋은 타점. MIN_ENTRY_QUALITY 미만은 신호 무시.

    기준:
    1) RSI < 65  (과매수 아닌 구간)
    2) 거래량 확인  (현재봉 > 20봉 평균)
    3) EMA 정배열  (EMA9 > EMA21 > EMA50)
    4) 구간 첫 번째 접촉  (신선한 구간)
    5) 진입 캔들 구조  (꼬리 긴 핀바/해머)
    6) VWAP 위  (가격이 VWAP 이상)
    7) 직전 스윙로우 위  (구조적 지지)
    """
    if len(df) < 30:
        return 0, []

    c   = df['Close']
    scores: list[str] = []

    # 1) RSI 과매수 아님
    d = c.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    rsi = (100 - 100 / (1 + g / l.replace(0, float('nan')))).iloc[-1]
    if not float('nan') == rsi and rsi < 65:
        scores.append('RSI<65')

    # 2) 거래량 확인 (Volume > 20봉 평균)
    vol = df['Volume']
    if vol.sum() > 0:
        avg_vol = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > avg_vol * 0.8:
            scores.append('Vol_OK')

    # 3) EMA 정배열
    e9  = c.ewm(span=9,  adjust=False).mean().iloc[-1]
    e21 = c.ewm(span=21, adjust=False).mean().iloc[-1]
    e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    if e9 > e21 > e50:
        scores.append('EMA_Align')

    # 4) 구간 신선도: 진입가가 구간 내에서 첫 접촉인지 (zone_low 근처)
    recent_lows = df['Low'].tail(10).values
    touches = sum(1 for lo in recent_lows[:-1] if zone_low * 0.995 <= lo <= zone_low * 1.02)
    if touches <= 1:
        scores.append('Fresh_Zone')

    # 5) 핀바 / 해머 캔들 구조 (긴 아래꼬리)
    bar = df.iloc[-1]
    body = abs(float(bar['Close']) - float(bar['Open']))
    lower_wick = float(bar[['Open', 'Close']].min()) - float(bar['Low'])
    candle_range = float(bar['High']) - float(bar['Low'])
    if candle_range > 0 and lower_wick > body and lower_wick / candle_range > 0.35:
        scores.append('PinBar')

    # 6) VWAP 위 (세션 내 가격 우위)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vol_s = df['Volume'].replace(0, float('nan'))
    vwap = (tp * vol_s).cumsum() / vol_s.cumsum()
    if not float('nan') == vwap.iloc[-1] and float(c.iloc[-1]) >= float(vwap.iloc[-1]) * 0.998:
        scores.append('Above_VWAP')

    # 7) 직전 스윙로우 위 (최근 10봉 최저점 위)
    swing_low = float(df['Low'].tail(10).iloc[:-1].min())
    if entry > swing_low * 0.998:
        scores.append('Above_SwingLow')

    return len(scores), scores


def _check_signal(df: pd.DataFrame) -> dict | None:
    """
    최근 봉 기준으로 FVG/OB 되돌림 진입 신호 체크
    Returns: 신호 딕셔너리 or None
    """
    if len(df) < 30: return None

    all_zones = sorted(_detect_fvg(df) + _detect_ob(df),
                       key=lambda z: z['formed_i'])

    # 아직 유효한 구간만 (마지막 봉 기준)
    last_i = len(df) - 1
    active = [z for z in all_zones
              if z['formed_i'] < last_i and z['expire_i'] > last_i]

    if not active: return None

    bar = df.iloc[last_i]
    hi  = float(bar['High'])
    lo  = float(bar['Low'])
    cl  = float(bar['Close'])
    op  = float(bar['Open'])

    for z in reversed(active):   # 최신 구간 우선
        zh = z['zone_high']
        zl = z['zone_low']

        # 가격이 구간에 되돌아왔는지
        if lo <= zh and cl >= zl:
            entry  = min(op, zh) if op <= zh else zh
            sl_pct = (entry - zl) / entry
            if not (MIN_SL_PCT <= sl_pct <= MAX_SL_PCT):
                continue

            sl = entry - entry * sl_pct
            tp = entry + entry * sl_pct * RR_RATIO

            # ── 진입 품질 점수 (참고용, 필터링 안함) ─────────
            # 백테스트 결과: FVG+OB 단독이 필터 적용보다 총수익 +31.76% vs +6.32%
            # 품질 점수는 대시보드 표시용으로만 사용
            quality_score, quality_tags = _entry_quality_score(df, entry, zl)

            return {
                'type':          z['type'],
                'entry':         round(entry, 4),
                'sl':            round(sl, 4),
                'tp':            round(tp, 4),
                'sl_pct':        round(-sl_pct * 100, 2),
                'tp_pct':        round(sl_pct * RR_RATIO * 100, 2),
                'zone_high':     zh,
                'zone_low':      zl,
                'formed_bar':    z['formed_i'],
                'quality_score': quality_score,      # 참고용 (0~7)
                'quality_tags':  ','.join(quality_tags),
            }
    return None


def scan_all() -> list:
    """전 종목 FVG+OB 신호 스캔 (KR5 + US5 + CRYPTO4)"""
    signals = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"\n{'='*65}")
    print(f"  FVG+OB Forward Scanner [{now_str}]")
    print(f"  KR 5종목 + US 5종목 + CRYPTO 4종목 (15분봉)")
    print(f"{'='*65}\n")

    # ── 한국주식 ────────────────────────────────────────────
    print("  [한국주식]")
    for code, (name, yf_tk, interval) in KR_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal(df)
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:,.0f} | 진입={sig['entry']:,.0f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker': code, 'name': name, 'market': 'KR',
                            'price': price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:,.0f} | 신호없음")

    # ── 미국주식 ────────────────────────────────────────────
    print("\n  [미국주식]")
    for code, (name, yf_tk, interval) in US_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal(df)
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:.2f} | 진입={sig['entry']:.2f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker': code, 'name': name, 'market': 'US',
                            'price': price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:.2f} | 신호없음")

    # ── 암호화폐 ────────────────────────────────────────────
    print("\n  [암호화폐]")
    for code, (name, yf_tk, interval) in CRYPTO_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal(df)
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:.2f} | 진입={sig['entry']:.2f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker': code, 'name': name, 'market': 'CRYPTO',
                            'price': price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:.2f} | 신호없음")

    print(f"\n  {'='*40}")
    print(f"  총 신호: {len(signals)}건")
    for s in signals:
        print(f"  >>> {s['name']} | {s['type']} | "
              f"진입={s['entry']} TP=+{s['tp_pct']:.2f}% SL={s['sl_pct']:.2f}%")
    print(f"{'='*65}\n")

    return signals


if __name__ == '__main__':
    scan_all()
