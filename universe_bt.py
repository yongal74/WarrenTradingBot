# -*- coding: utf-8 -*-
"""
유니버스 확대 백테스트 V3 (2026-04-28)
변경 로그:
  [V1→V2] KR/US RSI 조건: < 50 → < 60 (신호 빈도 목적)
  [V1→V2] CRYPTO Vol_Spike + Body_In_Zone 필터 추가
  [V2→V3] KR/US DBB 조건 제거 (신호 병목 원인)
           → 조건: EMA200 위 + RSI < 60 + FVG/OB 존 터치
  [V2→V3] 데이터 기간 1y → 5y (샘플 수 확보)
  목표: KR/US 월 5~15건 신호, CRYPTO WR 40%+
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import urllib.request, json
import pandas as pd
import numpy as np

# ── 파라미터 ──────────────────────────────────────────────────
SL_PCT       = 0.03
TP_PCT       = 0.06
MAX_HOLD     = 15
ZONE_EXPIRE  = 30
FEE = {'KR': 0.0023, 'US': 0.0050, 'CRYPTO': 0.0010}
BB_PERIOD = 20

# ── 후보 유니버스 ────────────────────────────────────────────
KR_CANDIDATES = {
    # 기존 5종목
    '005930.KS': ('삼성전자',         'KR'),
    '000660.KS': ('SK하이닉스',       'KR'),
    '009150.KS': ('삼성전기',         'KR'),
    '034020.KS': ('두산에너빌리티',   'KR'),
    '008060.KS': ('대덕전자',         'KR'),
    # 추가 후보 10종목
    '005380.KS': ('현대차',           'KR'),
    '000270.KS': ('기아',             'KR'),
    '035720.KS': ('카카오',           'KR'),
    '035420.KS': ('NAVER',            'KR'),
    '051910.KS': ('LG화학',           'KR'),
    '006400.KS': ('삼성SDI',          'KR'),
    '373220.KS': ('LG에너지솔루션',   'KR'),
    '247540.KS': ('에코프로비엠',     'KR'),
    '068270.KS': ('셀트리온',         'KR'),
    '105560.KS': ('KB금융',           'KR'),
}

US_CANDIDATES = {
    # 기존 5종목
    'NVDA':  ('엔비디아',    'US'),
    'PLTR':  ('팔란티어',    'US'),
    'AMD':   ('AMD',         'US'),
    'TSLA':  ('테슬라',      'US'),
    'SOXX':  ('반도체ETF',   'US'),
    # 추가 후보 10종목
    'META':  ('메타',        'US'),
    'MSFT':  ('마이크로소프트','US'),
    'GOOGL': ('구글',        'US'),
    'AMZN':  ('아마존',      'US'),
    'COIN':  ('코인베이스',  'US'),
    'MSTR':  ('마이크로스트래티지','US'),
    'CRWD':  ('크라우드스트라이크','US'),
    'SMCI':  ('슈퍼마이크로','US'),
    'ARM':   ('ARM홀딩스',   'US'),
    'IONQ':  ('아이온큐',    'US'),
}

CRYPTO_CANDIDATES = {
    # 기존 4종목
    'BTC-USD': ('비트코인',    'CRYPTO'),
    'ETH-USD': ('이더리움',    'CRYPTO'),
    'SOL-USD': ('솔라나',      'CRYPTO'),
    'XRP-USD': ('리플',        'CRYPTO'),
    # 추가 후보 11종목
    'BNB-USD':  ('바이낸스코인','CRYPTO'),
    'DOGE-USD': ('도지코인',   'CRYPTO'),
    'ADA-USD':  ('에이다',     'CRYPTO'),
    'AVAX-USD': ('아발란체',   'CRYPTO'),
    'LINK-USD': ('체인링크',   'CRYPTO'),
    'DOT-USD':  ('폴카닷',     'CRYPTO'),
    'MATIC-USD':('폴리곤',     'CRYPTO'),
    'ATOM-USD': ('코스모스',   'CRYPTO'),
    'UNI-USD':  ('유니스왑',   'CRYPTO'),
    'LTC-USD':  ('라이트코인', 'CRYPTO'),
    'TRX-USD':  ('트론',       'CRYPTO'),
}


# ── 데이터 로드 ─────────────────────────────────────────────
def _fetch(ticker: str, interval: str, range_str: str) -> pd.DataFrame | None:
    imap = {'1d':'1d','1h':'60m'}
    yf_iv = imap.get(interval, interval)
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval={yf_iv}&range={range_str}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        r = data.get('chart',{}).get('result',[])
        if not r: return None
        r = r[0]
        ts = r.get('timestamp',[])
        if not ts: return None
        q = r.get('indicators',{}).get('quote',[{}])[0]
        adj = r.get('indicators',{}).get('adjclose',[])
        closes = (adj[0].get('adjclose',[]) if adj and isinstance(adj[0],dict) and adj[0].get('adjclose')
                  else q.get('close',[]))
        df = pd.DataFrame({
            'Open': q.get('open',[]), 'High': q.get('high',[]),
            'Low':  q.get('low',[]),  'Close': closes,
            'Volume': q.get('volume',[]),
        }, index=pd.to_datetime(ts, unit='s', utc=True).tz_convert(None))
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return None


def load_daily(ticker: str) -> pd.DataFrame | None:
    # V3: 5년 데이터로 확대 (샘플 수 확보)
    df = _fetch(ticker, '1d', '5y')
    if df is not None and len(df) >= 50:
        return df
    return _fetch(ticker, '1d', '2y')  # fallback


def load_4h(ticker: str) -> pd.DataFrame | None:
    df1h = _fetch(ticker, '1h', '3mo')
    if df1h is None or len(df1h) < 30: return None
    df4h = df1h.resample('4h').agg({
        'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'
    }).dropna()
    return df4h if len(df4h) >= 30 else None


# ── 지표 ────────────────────────────────────────────────────
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df['Close']
    df['ema200'] = c.ewm(span=200, adjust=False).mean()
    ma = c.rolling(BB_PERIOD).mean()
    sd = c.rolling(BB_PERIOD).std()
    df['bb1_lower'] = ma - 1.0 * sd
    d = c.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    df['rsi'] = 100 - 100 / (1 + g / l.replace(0, float('nan')))
    return df


def detect_fvg(df: pd.DataFrame, min_gap: float = 0.003) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > min_gap:
            zones.append({'type':'FVG','formed_i':i,
                          'zone_high':lo0,'zone_low':hi2,'expire_i':i+ZONE_EXPIRE})
    return zones


def detect_ob(df: pd.DataFrame, min_impulse: float = 0.005) -> list:
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > min_impulse:
            zones.append({'type':'OB','formed_i':i,
                          'zone_high':float(b['High']),'zone_low':float(b['Low']),
                          'expire_i':i+ZONE_EXPIRE})
    return zones


# ── 스윙 백테스트 (KR/US) ────────────────────────────────────
def run_swing_bt(df: pd.DataFrame, market: str) -> list:
    if len(df) < 220: return []
    df = add_indicators(df)
    zones = detect_fvg(df) + detect_ob(df)
    fee = FEE[market]
    trades = []
    in_trade = False

    for i in range(200, len(df)):
        if in_trade:
            row = df.iloc[i]
            days = i - entry_i
            if float(row['High']) >= tp_price:
                trades.append({'result':'WIN','pnl_gross':TP_PCT,'pnl_net':TP_PCT-fee,'hold':days,'type':z_type})
                in_trade = False
            elif float(row['Low']) <= sl_price:
                trades.append({'result':'LOSS','pnl_gross':-SL_PCT,'pnl_net':-SL_PCT-fee,'hold':days,'type':z_type})
                in_trade = False
            elif days >= MAX_HOLD:
                cl = float(df['Close'].iloc[i])
                pg = (cl - entry_price) / entry_price
                trades.append({'result':'WIN' if pg>0 else 'LOSS','pnl_gross':pg,'pnl_net':pg-fee,'hold':days,'type':z_type})
                in_trade = False
            continue

        row = df.iloc[i]
        cl     = float(row['Close'])
        lo     = float(row['Low'])
        ema200 = float(row['ema200'])
        rsi    = float(row['rsi'])

        if pd.isna(ema200) or pd.isna(rsi): continue
        # [V3] DBB 조건 제거 — 신호 병목 원인 확인됨 (2026-04-28)
        # 조건: EMA200 위 (추세 확인) + RSI < 60 (과매수 아님) + FVG/OB 존 터치
        if cl < ema200 * 0.98: continue   # EMA200 아래 2% → 추세 하락
        if rsi >= 60: continue             # RSI >= 60 → 과매수

        active = [z for z in zones if z['formed_i'] < i and z['expire_i'] > i]
        for z in reversed(active):
            if lo <= z['zone_high'] and cl >= z['zone_low']:
                in_trade = True
                entry_i = i
                entry_price = cl
                tp_price = cl * (1 + TP_PCT)
                sl_price = cl * (1 - SL_PCT)
                z_type = z['type']
                break

    return trades


# ── 4H 백테스트 (CRYPTO) ────────────────────────────────────
# [V2 변경] 진입 필터 2개 추가 (WR 25~38% → 40%+ 목표, 2026-04-28)
# 필터1: Vol_Spike — 현재봉 거래량 > 20봉 평균 × 1.5 (기관 개입 확인)
# 필터2: Body_In_Zone — 종가가 존 중간(50%) 이상에서 마감 (Fake 캔들 제거)
def run_4h_bt(df: pd.DataFrame) -> list:
    if len(df) < 30: return []
    fee = FEE['CRYPTO']
    zones = detect_fvg(df, 0.005) + detect_ob(df, 0.003)
    trades = []
    in_trade = False
    RR = 3.0

    for i in range(10, len(df)):
        if in_trade:
            row = df.iloc[i]
            bars = i - entry_i
            if float(row['High']) >= tp_price:
                trades.append({'result':'WIN','pnl_gross':tp_pct,'pnl_net':tp_pct-fee,'hold':bars,'type':z_type})
                in_trade = False
            elif float(row['Low']) <= sl_price:
                trades.append({'result':'LOSS','pnl_gross':-sl_pct,'pnl_net':-sl_pct-fee,'hold':bars,'type':z_type})
                in_trade = False
            elif bars >= 15 * 6:  # 최대 15일 (4H 봉 15*6=90개)
                cl2 = float(df['Close'].iloc[i])
                pg = (cl2 - entry_price) / entry_price
                trades.append({'result':'WIN' if pg>0 else 'LOSS','pnl_gross':pg,'pnl_net':pg-fee,'hold':bars,'type':z_type})
                in_trade = False
            continue

        row = df.iloc[i]
        cl  = float(row['Close'])
        lo  = float(row['Low'])
        vol = float(row['Volume'])

        # [V2] 필터1: Vol_Spike — 20봉 평균 대비 1.5배 이상
        vol_series = df['Volume'].iloc[max(0,i-20):i]
        avg_vol = float(vol_series.mean()) if len(vol_series) > 0 else 0
        has_vol_spike = (avg_vol > 0 and vol > avg_vol * 1.5)

        active = [z for z in zones if z['formed_i'] < i and z['expire_i'] > i]
        for z in reversed(active):
            if lo <= z['zone_high'] and cl >= z['zone_low']:
                # [V2] 필터2: Body_In_Zone — 종가가 존 중간 이상
                zone_mid = z['zone_low'] + (z['zone_high'] - z['zone_low']) * 0.5
                if cl < zone_mid: continue  # 존 하단에만 걸친 Fake 캔들 제거
                # [V2] 필터1 적용: Vol_Spike 필수
                if not has_vol_spike: continue

                raw_sl = (cl - z['zone_low']) / cl if cl > 0 else 0.01
                sl_pct_v = max(raw_sl, 0.005)
                if sl_pct_v > 0.03: continue  # 너무 넓으면 스킵
                tp_pct_v = sl_pct_v * RR
                in_trade = True
                entry_i = i
                entry_price = cl
                sl_pct = sl_pct_v
                tp_pct = tp_pct_v
                sl_price = cl * (1 - sl_pct_v)
                tp_price = cl * (1 + tp_pct_v)
                z_type = z['type']
                break

    return trades


# ── 성과 요약 ────────────────────────────────────────────────
def summarize(trades: list, market: str) -> dict:
    if not trades:
        return {'count':0,'wr':0,'net_pnl':0,'ev':0,'mdd':0}
    df = pd.DataFrame(trades)
    wins = (df['result']=='WIN').sum()
    wr   = wins / len(df) * 100
    net  = df['pnl_net'].sum() * 100
    ev   = df['pnl_net'].mean() * 100
    cum  = df['pnl_net'].cumsum()
    mdd  = ((cum - cum.cummax()) / (1 + cum.cummax())).min() * 100
    return {'count':len(df),'wr':round(wr,1),'net_pnl':round(net,2),
            'ev':round(ev,3),'mdd':round(mdd,2)}


# ── 메인 ─────────────────────────────────────────────────────
def main():
    results = []

    # KR 스윙 백테스트
    print('\n' + '='*65)
    print('  [KR] 스윙 백테스트 V3 (FVG+OB+EMA200+RSI<60, 일봉 5년, DBB제거)')
    print('='*65)
    for ticker, (name, market) in KR_CANDIDATES.items():
        df = load_daily(ticker)
        if df is None or len(df) < 220:
            print(f'  {name:<16} 데이터 부족')
            continue
        trades = run_swing_bt(df, market)
        s = summarize(trades, market)
        flag = '★' if s['ev'] > 1.0 and s['wr'] > 55 else ' '
        print(f'  {flag}{name:<16} {s["count"]:3d}건 | WR {s["wr"]:5.1f}% | '
              f'순수익 {s["net_pnl"]:+7.2f}% | EV {s["ev"]:+.3f}% | MDD {s["mdd"]:+.2f}%')
        results.append({'market':market,'ticker':ticker,'name':name,**s})

    # US 스윙 백테스트
    print('\n' + '='*65)
    print('  [US] 스윙 백테스트 V3 (FVG+OB+EMA200+RSI<60, 일봉 5년, DBB제거)')
    print('='*65)
    for ticker, (name, market) in US_CANDIDATES.items():
        df = load_daily(ticker)
        if df is None or len(df) < 220:
            print(f'  {name:<20} 데이터 부족')
            continue
        trades = run_swing_bt(df, market)
        s = summarize(trades, market)
        flag = '★' if s['ev'] > 0.8 and s['wr'] > 50 else ' '
        print(f'  {flag}{name:<20} {s["count"]:3d}건 | WR {s["wr"]:5.1f}% | '
              f'순수익 {s["net_pnl"]:+7.2f}% | EV {s["ev"]:+.3f}% | MDD {s["mdd"]:+.2f}%')
        results.append({'market':market,'ticker':ticker,'name':name,**s})

    # CRYPTO 4H 백테스트
    print('\n' + '='*65)
    print('  [CRYPTO] 4H 백테스트 (FVG+OB zone-SL, R:R 1:3)')
    print('='*65)
    for ticker, (name, market) in CRYPTO_CANDIDATES.items():
        df = load_4h(ticker)
        if df is None or len(df) < 30:
            print(f'  {name:<16} 데이터 부족')
            continue
        trades = run_4h_bt(df)
        s = summarize(trades, market)
        flag = '★' if s['ev'] > 0.5 and s['wr'] > 50 else ' '
        print(f'  {flag}{name:<16} {s["count"]:3d}건 | WR {s["wr"]:5.1f}% | '
              f'순수익 {s["net_pnl"]:+7.2f}% | EV {s["ev"]:+.3f}% | MDD {s["mdd"]:+.2f}%')
        results.append({'market':market,'ticker':ticker,'name':name,**s})

    # ── 시장별 TOP 랭킹 ──────────────────────────────────────
    df_res = pd.DataFrame(results)

    for mkt, n_target in [('KR',10),('US',10),('CRYPTO',11)]:
        sub = df_res[df_res['market']==mkt].copy()
        sub = sub[sub['count'] >= 3]
        sub['score'] = sub['wr'] * 0.4 + sub['ev'] * 20 - sub['mdd'].abs() * 0.5
        top = sub.nlargest(n_target, 'score')
        print(f'\n{"="*65}')
        print(f'  [{mkt}] 추천 상위 {n_target}종목 (EV×20 + WR×0.4 - MDD×0.5)')
        print(f'{"="*65}')
        for rank, (_, row) in enumerate(top.iterrows(), 1):
            print(f'  {rank:2d}. {row["name"]:<18} WR {row["wr"]:5.1f}% | '
                  f'EV {row["ev"]:+.3f}% | 순수익 {row["net_pnl"]:+.2f}% | score {row["score"]:.1f}')

    # CSV 저장
    df_res.to_csv('logs/universe_bt_result.csv', index=False, encoding='utf-8-sig')
    print('\n  결과 저장: logs/universe_bt_result.csv')


if __name__ == '__main__':
    main()
