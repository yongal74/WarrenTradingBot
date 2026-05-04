# -*- coding: utf-8 -*-
"""
FVG + Order Block 포워드 테스터
백테스트와 동일한 로직으로 실시간 신호 감지

5-Pillar 연동:
  HALT        → 전면 차단
  DEFENSIVE   → FVG+OB + 7점 품질 필터 (3점 이상)
  NORMAL      → 순수 FVG+OB (필터 없음, 백테스트 최고 성과)
  AGGRESSIVE  → 순수 FVG+OB (필터 없음)
"""
import warnings; warnings.filterwarnings('ignore')
import sys, pandas as pd, yfinance as yf
from datetime import datetime
from pathlib import Path

# KR 실시간 현재가: KIS API 1순위 → FinanceDataReader 2순위 → yfinance 3순위
def _kr_current_price(code: str) -> float | None:
    """KR 종목 당일 현재가 조회.

    우선순위:
      1. KIS API (get_price) — 실시간, 가장 정확
      2. FinanceDataReader — KIS 실패 시 fallback
      3. 둘 다 실패 시 None 반환
    """
    # 1순위: KIS API
    try:
        from core.kis_trader import get_price as _kis_get_price
        p = _kis_get_price(code)
        if p and p > 0:
            return float(p)
    except Exception:
        pass
    # 2순위: FinanceDataReader
    try:
        import FinanceDataReader as fdr
        today = datetime.now().strftime('%Y-%m-%d')
        df = fdr.DataReader(code, today)
        if df is not None and not df.empty:
            return float(df['Close'].iloc[-1])
    except Exception:
        pass
    return None

# Windows 콘솔 UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from core.macro_regime import get_regime, min_quality_by_regime

# ── 파라미터 ──────────────────────────────────────────────────
# 2026-04-28 최종: 시장별 SL/TP 전략 확정
#
# CRYPTO (4H 전용): SL = zone 기반 가변 (초기 백테스트 방식 복원)
#   → 4H WR 61% / PnL +400% 검증됨. zone SL이 더 구조적으로 정확
#   → R:R 3.0 유지 (TP = zone_sl × 3)
#   → SL floor 0.5% (너무 작은 zone 제외), 상한 3% (4H 특성상 넓음)
#
# KR (15m 단타): SL 1% floor / TP 2% — 스윙 전환 검토 중
# US (15m 단타): SL 1% floor / TP 2% — 스윙 전환 검토 중

SL_BY_MARKET = {
    'KR':     0.010,   # 1.0% SL floor
    'US':     0.010,   # 1.0% SL floor
    'CRYPTO': None,    # zone 기반 가변 (4H, 아래 로직에서 처리)
}
RR_BY_MARKET = {
    'KR':     2.0,     # R:R 1:2 → TP 2%
    'US':     2.0,     # R:R 1:2 → TP 2%
    'CRYPTO': 3.0,     # R:R 1:3 → TP = zone_sl × 3
}

# 전역 기본값 (market 정보 없을 때 fallback)
RR_RATIO     = 2.0
FIXED_SL_PCT = 0.010   # KR/US SL 1% floor
FIXED_TP_PCT = 0.020   # KR/US TP 2%
MAX_SL_PCT   = 0.030   # CRYPTO 4H zone 상한 3% (4H 봉 크기 감안)
MIN_SL_PCT   = 0.001   # zone 하한
ZONE_EXPIRE  = 20      # 봉 기준

# ── 진입 품질 필터 기준 ───────────────────────────────────
MIN_ENTRY_QUALITY = 4   # 2026-04-30 V4.6 원복: 3→4 (케이스 30건↑ 달성, 품질 강화)

# ── 시장별 실전 수수료 (왕복) + 순수익 기준 ──────────────────
# KR:     수수료 0.23% → TP 2.0% → 순수익 1.77%
# US:     수수료 0.50% → TP 2.0% → 순수익 1.50%
# CRYPTO: 수수료 0.10% → TP 3.0% → 순수익 2.90%
MIN_TP_BY_MARKET = {
    'KR':     1.50,   # 수수료 0.23% + 순수익 1.27% 보장
    'US':     1.50,   # 수수료 0.50% + 순수익 1.00% 보장
    'CRYPTO': 2.50,   # 수수료 0.10% + 순수익 2.40% 보장
}

# ── 시장별 거래 허용 시간대 (KST) ────────────────────────────
# KR:     09:00~16:30 (장중 09~15:30 + 애프터 1시간)
# US:     22:30~06:00 (장중 22:30~05:00 + 애프터 1시간)  ← 분 단위는 hour로 근사
# CRYPTO: 24/7 제한 없음
MARKET_HOURS_KST = {
    'KR':     set(range(9, 17)),          # 09~16시 (16:30 근사)
    'US':     set(range(22, 24)) | set(range(0, 7)),  # 22~06시
    'CRYPTO': set(range(0, 24)),          # 전 시간
}

# ── 5분봉 확인 캔들 설정 (2026-04-28 추가) ───────────────────
# USE_5M_CONFIRM = True  → 15m 신호 감지 후 5m 양봉 마감 확인 필수
# USE_5M_CONFIRM = False → 기존 방식 (15m만 사용, 더 빠른 진입)
# A/B 비교: 둘 다 로깅 후 성과 비교
USE_5M_CONFIRM = True       # 5m 양봉 확인 캔들 필수 (2026-04-28 ON 전환)

# ── 주봉 HTF 필터 (2026-04-28 추가) ──────────────────────────
# CRYPTO 4H 신호 발생 시 주봉 EMA20 위인지 확인
# 근거: XRP 백테스트 HTF 적용 시 WR +16.1%p 개선 (36%→52%)
# 적용: CRYPTO 4H 전용 (KR/US 스윙은 별도 EMA200 필터 사용 중)
USE_HTF_WEEKLY = True       # 주봉 EMA20 위 필터 ON

# ── 하루 최대 거래 건수 (Flexible: 품질별 차등) ─────────────
MAX_DAILY_SIGNALS   = 10   # 하드 상한
MIN_DAILY_SIGNALS   = 5    # 최소 보장 (품질 무관)
# Q=6~7 → 무조건 포함 / Q=4~5 → 상위 5건 / 전체 최대 10건

# ── KR/US 15m 단타 비활성화 (2026-04-28) ──────────────────────────
# 근거: KR 수수료 0.23% / US 0.50% → 15m 단타 수익이 수수료 대비 박함
# 버전 비교 백테스트: CRYPTO V2만 수수료 후 순수익 흑자. KR/US 적자
# → KR/US 스윙 전략 (일봉 FVG+OB+DBB+EMA200) 으로 전환
# 코드 보존: SWING_MODE_KR/US = False 로 변경 시 15m 복구 가능
SWING_MODE_KR = True   # True: 스윙(일봉), False: 15m 단타 (비활성화)
SWING_MODE_US = True   # True: 스윙(일봉), False: 15m 단타 (비활성화)

# 15m 단타용 티커 (SWING_MODE=False 시 사용, 현재 비활성화)
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

# ── 스윙 유니버스 (일봉 FVG+OB+EMA200) ── 2026-04-28 V4_RELAXED 반영 ──────
# V4 변경사항 (2026-04-28):
#   - 진입조건 완화: BB1하단→MA20이하 / RSI<60→RSI<70 / 품질4→3점
#   - 목적: 포워드테스팅 케이스 축적 (잠정 조치, 케이스 30건 후 원본과 비교)
#   - KR 제외: 두산에너빌리티(Score 25), NAVER(Score 21) — V4 완화에서도 하위
#   - US 제외: TSLA(EV -0.45%, 완화조건에서도 마이너스) — 퇴출
#   - US 신규: RTX(WR92.9%★), QQQI(WR100%★), 에르메스ADR(WR86.7%★)
#   - JP 신규: 닛토방적(WR84.6%) — 관찰 시작 (데이터 축적 후 판단)
KR_SWING_TICKERS = {
    # V4.0 기존 8종목
    '017670': ('SK텔레콤',       '017670.KS'),   # BB반등 WR85.7% EV+5.23%
    '035720': ('카카오',         '035720.KS'),   # BB반등 WR81.8% EV+2.44%
    '021240': ('코웨이',         '021240.KS'),   # BB반등 WR78.6% EV+2.67%
    '005380': ('현대차',         '005380.KS'),   # BB반등 WR77.8% EV+3.82%
    '010140': ('삼성중공업',     '010140.KS'),   # SuperTrend WR75.0%
    '086790': ('하나금융',       '086790.KS'),   # MACD WR73.3%
    '034020': ('두산에너빌',     '034020.KS'),   # BB반등 WR66.7%
    '272210': ('한화시스템',     '272210.KS'),   # GapGo WR60.0%
    # V4.1 신규 편입 5종목 (2026-04-29 백테스트 검증)
    '000660': ('SK하이닉스',     '000660.KS'),   # 반도체 WR55.1% EV+1.303% PF=2.45
    '058470': ('리노공업',       '058470.KS'),   # 반도체 WR51.7% EV+1.121% PF=2.18
    '064350': ('현대로템',       '064350.KS'),   # 방산   WR48.4% EV+0.906% PF=1.88
    '128940': ('한미약품',       '128940.KS'),   # 바이오 WR44.2% EV+0.653% PF=1.58
    '012450': ('한화에어로스페이스','012450.KS'), # 방산   WR43.7% EV+0.637% PF=1.57
    # V4.5 추가 (2026-04-29)
    '005930': ('삼성전자',       '005930.KS'),   # 반도체 WR56.5%
    '009150': ('삼성전기',       '009150.KS'),   # 반도체 WR52.9%
    '008060': ('대덕전자',       '008060.KS'),   # 반도체 WR56.5%
}

# V4 US: TSLA 퇴출(EV-0.45%), RTX/QQQI/HESAY 신규 편입
US_SWING_TICKERS = {
    # V4.0 기존 5종목
    'AMD':  ('AMD',               'AMD'),   # WR87.5% EV+1.89%
    'MU':   ('마이크론',          'MU'),    # WR80.0% EV+1.96%
    'NVDA': ('엔비디아',          'NVDA'),  # WR72.7% EV+1.27%
    'AVGO': ('브로드컴',          'AVGO'),  # WR66.7% EV+2.75%
    'MSTR': ('마이크로스트레티지', 'MSTR'), # WR60.0% EV+3.10%
    # V4.1 신규 편입 5종목 (2026-04-29 백테스트 검증)
    'LRCX': ('램리서치',          'LRCX'),  # WR42.4% EV+0.566% PF=1.50
    'AMZN': ('아마존',            'AMZN'),  # WR41.0% EV+0.460% PF=1.39
    'SHOP': ('쇼피파이',          'SHOP'),  # WR38.7% EV+0.321% PF=1.26
    'GOOGL':('구글',              'GOOGL'), # WR38.5% EV+0.312% PF=1.25
    'TSLA': ('테슬라',            'TSLA'),  # WR37.5% EV+0.250% PF=1.20
}

# ── JP 유니버스 (신규, 관찰 시작) ─────────────────────────────────
# 2026-04-28 V4: 닛토방적(WR84.6%), JX어드밴스드메탈스(데이터1건) 추가
# JP는 .T 티커 (Tokyo Stock Exchange), 수수료 0.3% 적용
SWING_MODE_JP = True   # True: JP 스윙 스캔 활성화
JP_SWING_TICKERS = {
    '3110.T': ('닛토방적',         '3110.T'),  # V4 WR84.6% EV+2.53% Score=80
    '5016.T': ('JX어드밴스드메탈스','5016.T'), # V4 데이터1건 → 관찰
}

# 스윙 SL/TP 파라미터
SWING_SL_FLOOR  = 0.020   # 2% 최소 SL (일봉 변동성 고려)
SWING_SL_CAP    = 0.080   # 8% 최대 SL
SWING_MAX_HOLD  = 15      # 최대 보유일

# CRYPTO 15m: 2026-04-28 재활성화
# 근거: 수수료 0.10%로 15m도 흑자 가능 (원본 백테스트 WR=51%, PnL=+13.8%/2년)
# 4H 포지션 없는 종목에만 진입 → 자본 충돌 방지
# 4H+15m 병행 시 월수익 +0.58%p 추가 기대
CRYPTO_TICKERS = {
    'BTC':  ('비트코인',  'BTC-USD',  '15m'),
    'ETH':  ('이더리움',  'ETH-USD',  '15m'),
    'SOL':  ('솔라나',    'SOL-USD',  '15m'),
    'XRP':  ('리플',      'XRP-USD',  '15m'),
}

# ── 4H 전용 유니버스 ── 2026-04-28 V3 백테스트 결과 반영 (15종목) ──
# V3 CRYPTO Top: DOGE WR43.5% EV+0.775% / BTC WR37% EV+0.594% / ADA WR27.3% EV+0.607%
# 4H 필터: Vol_Spike(vol>avg*1.5) + Body_In_Zone(close>=zone_mid) 적용
CRYPTO_4H_TICKERS = {
    # V4.6 FVG+OB 4H 4종목 확정 (2026-04-30, R:R 1:3)
    # 정책: CRYPTO_TICKERS(15m) 4종목과 동일하게 유지 → 일관된 유니버스
    # DOGE 제외: 15m 유니버스에 없고, 백테스트 데이터 불안정
    # ETH 추가: 15m과 동일 종목, 4H도 FVG+OB 성과 안정적
    'BTC':  ('비트코인',  'BTC-USD'),   # WR31.5% EV+0.187% 월+1.41%
    'ETH':  ('이더리움',  'ETH-USD'),   # 4H 신규 추가 (15m과 통일)
    'SOL':  ('솔라나',    'SOL-USD'),   # WR28.5% EV+0.209% 월+1.81%
    'XRP':  ('리플',      'XRP-USD'),   # WR26.9% EV+0.137% 월+1.21%
}

US_4H_TICKERS = {
    'NVDA': ('엔비디아',  'NVDA'),
    'RTX':  ('RTX',       'RTX'),   # 2026-04-28 TSLA 대체 (WR92.9%)
    'AMD':  ('AMD',       'AMD'),
}


def _yahoo_fetch(ticker: str, interval: str = '1d', range_str: str = '1y') -> pd.DataFrame | None:
    """
    Yahoo Finance v8 API 직접 호출 (yfinance 1.3.0 호환성 문제 우회)
    interval: 1m/5m/15m/1h/1d  |  range_str: 1d/5d/1mo/3mo/6mo/1y/2y/5y
    """
    import urllib.request, json, time as _time
    interval_map = {'1m':'1m','5m':'5m','15m':'15m','1h':'60m','4h':'60m','1d':'1d'}
    yf_interval = interval_map.get(interval, interval)
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval={yf_interval}&range={range_str}')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        result = data.get('chart', {}).get('result', [])
        if not result:
            return None
        r = result[0]
        timestamps = r.get('timestamp', [])
        if not timestamps:
            return None
        ohlcv = r.get('indicators', {}).get('quote', [{}])[0]
        # adjclose: 주식만 존재, CRYPTO/지수는 close 사용
        adj_list = r.get('indicators', {}).get('adjclose', [])
        if adj_list and isinstance(adj_list[0], dict) and adj_list[0].get('adjclose'):
            closes = adj_list[0]['adjclose']
        else:
            closes = ohlcv.get('close', [])
        df = pd.DataFrame({
            'Open':   ohlcv.get('open',   []),
            'High':   ohlcv.get('high',   []),
            'Low':    ohlcv.get('low',    []),
            'Close':  closes,
            'Volume': ohlcv.get('volume', []),
        }, index=pd.to_datetime(timestamps, unit='s', utc=True).tz_convert(None))
        df = df[['Open','High','Low','Close','Volume']].dropna()
        # 4h 리샘플은 호출부에서 별도 처리
        return df
    except Exception:
        return None


def _load_daily(yf_ticker: str) -> pd.DataFrame | None:
    """일봉 1년치 로드 (스윙 전략용) — v8 API 직접 호출"""
    df = _yahoo_fetch(yf_ticker, '1d', '1y')
    if df is not None and len(df) >= 50:
        return df
    # fallback: yf.download
    try:
        df2 = yf.download(yf_ticker, period='1y', interval='1d',
                          auto_adjust=True, progress=False)
        if df2 is None or df2.empty: return None
        if hasattr(df2.columns, 'levels'): df2.columns = df2.columns.droplevel(1)
        if df2.index.tz is not None: df2.index = df2.index.tz_localize(None)
        return df2[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return None


def _add_swing_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """스윙 지표: EMA200, Double BB(20,1σ/2σ), RSI14"""
    df = df.copy()
    c = df['Close']
    df['ema200']    = c.ewm(span=200, adjust=False).mean()
    ma20            = c.rolling(20).mean()
    sd20            = c.rolling(20).std()
    df['bb1_lower'] = ma20 - 1.0 * sd20
    df['bb2_lower'] = ma20 - 2.0 * sd20
    df['bb_mid']    = ma20
    d = c.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    df['rsi'] = 100 - 100 / (1 + g / l.replace(0, float('nan')))
    return df


def _detect_fvg_daily(df: pd.DataFrame) -> list:
    """일봉 FVG 감지 (일봉 최소 갭 0.3%)"""
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.003:
            zones.append({'type': 'FVG', 'formed_i': i,
                          'zone_high': lo0, 'zone_low': hi2,
                          'expire_i': i + 30})
    return zones


def _detect_ob_daily(df: pd.DataFrame) -> list:
    """일봉 OB 감지 (임펄스 0.5% 이상)"""
    zones = []
    for i in range(1, len(df) - 2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.005:
            zones.append({'type': 'OB', 'formed_i': i,
                          'zone_high': float(b['High']),
                          'zone_low':  float(b['Low']),
                          'expire_i':  i + 30})
    return zones


def _check_swing_signal(df: pd.DataFrame, market: str) -> dict | None:
    """
    스윙 진입 신호 체크 (일봉 기준)
    [V4_RELAXED 2026-04-28] 케이스 축적 목적으로 조건 완화 (잠정):
      1. EMA200 위 (상승 추세, 2% 여유) ← 핵심 원칙 유지
      2. Close < MA20 (BB1하단→MA20이하 완화: 과매도 대신 단기 조정 구간)
      3. RSI(14) < 70 (RSI<50→<70 완화: 모멘텀 감속 구간)
      4. FVG 또는 OB 존 터치 ← 핵심 원칙 유지
    변경 이유: 기존 조건(BB1하단+RSI<50)이 너무 타이트 → 신호 0건 → 테스트 불가
    다음 단계: 케이스 30건↑ 후 원본 조건(V3)과 WR/EV 비교 후 최적 조건 확정
    """
    if len(df) < 220:
        return None
    df = _add_swing_indicators(df)
    last = df.iloc[-1]

    cl     = float(last['Close'])
    ema200 = float(last['ema200'])
    bb1_lo = float(last['bb1_lower'])
    bb_mid = float(last['bb_mid'])   # MA20
    rsi    = float(last['rsi'])

    if pd.isna(ema200) or pd.isna(bb_mid) or pd.isna(rsi):
        return None

    # 1) EMA200 위 (핵심 원칙 유지)
    if cl < ema200 * 0.98:
        return None

    # 2) BB1하단(1σ) 이하 (V4.6: MA20→BB1하단으로 강화. 기존 V3 원본 복원)
    # 근거: MA20 이하는 조건이 너무 넓어 승률 저하. 1σ 이하가 과매도 구간 정확히 포착.
    if cl > bb1_lo:
        return None

    # 3) RSI < 60 (V4.6: 70→60으로 강화. 과매수 근처 진입 차단)
    if rsi >= 60:
        return None

    # 4) FVG+OB 존 터치 (핵심 원칙 유지)
    all_zones = _detect_fvg_daily(df) + _detect_ob_daily(df)
    last_i = len(df) - 1
    active = [z for z in all_zones
              if z['formed_i'] < last_i and z['expire_i'] > last_i]
    if not active:
        return None

    lo = float(last['Low'])
    for z in reversed(active):
        zh = z['zone_high']
        zl = z['zone_low']
        if lo <= zh and cl >= zl:
            sl_pct = (cl - zl) / cl if cl > 0 else SWING_SL_FLOOR
            sl_pct = max(sl_pct, SWING_SL_FLOOR)
            sl_pct = min(sl_pct, SWING_SL_CAP)
            rr = RR_BY_MARKET.get(market, 2.0)
            tp_pct = sl_pct * rr
            tags = f'EMA200,MA20_Below,RSI<70,{z["type"]}'
            return {
                'type':          z['type'],
                'timeframe':     'daily',
                'entry':         round(cl, 4),
                'sl':            round(cl * (1 - sl_pct), 4),
                'tp':            round(cl * (1 + tp_pct), 4),
                'sl_pct':        round(-sl_pct * 100, 2),
                'tp_pct':        round(tp_pct * 100, 2),
                'zone_high':     zh,
                'zone_low':      zl,
                'formed_bar':    z['formed_i'],
                'quality_score': 3,
                'quality_tags':  tags,
                'ema200':        round(ema200, 2),
                'rsi':           round(rsi, 1),
                'bb1_lower':     round(bb1_lo, 2),
                'bb_mid':        round(bb_mid, 2),
            }
    return None


def _check_momentum_signal(df: pd.DataFrame, market: str) -> dict | None:
    """
    Momentum 진입 신호 체크 (일봉 기준) — S6_Momentum 전략
    조건 (AND):
      1. Close > EMA200  (장기 상승 추세)
      2. Close > EMA50   (중기 상승 추세)
      3. RSI 50~65       (모멘텀 구간, 과매수 아님)
      4. 20봉 수익률 > 3% (최근 상승 모멘텀)
    TP: entry × (1 + sl_pct × RR)   SL: entry × (1 - 2%)
    """
    if len(df) < 220:
        return None
    df = _add_swing_indicators(df)

    # EMA50 추가
    df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()

    last = df.iloc[-1]
    cl      = float(last['Close'])
    ema200  = float(last['ema200'])
    ema50   = float(last['ema50'])
    rsi     = float(last['rsi'])

    if any(pd.isna(v) for v in [ema200, ema50, rsi]):
        return None

    # 1) EMA200 위
    if cl < ema200:
        return None

    # 2) EMA50 위
    if cl < ema50:
        return None

    # 3) RSI 50~65 (모멘텀 구간)
    if not (50 <= rsi <= 65):
        return None

    # 4) 20봉 수익률 > 3%
    if len(df) < 21:
        return None
    cl_20 = float(df['Close'].iloc[-21])
    if cl_20 <= 0 or (cl - cl_20) / cl_20 < 0.03:
        return None

    sl_pct = SWING_SL_FLOOR  # 2% 고정
    rr = RR_BY_MARKET.get(market, 2.0)
    tp_pct = sl_pct * rr

    return {
        'type':          'Momentum',
        'timeframe':     'daily',
        'entry':         round(cl, 4),
        'sl':            round(cl * (1 - sl_pct), 4),
        'tp':            round(cl * (1 + tp_pct), 4),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl,
        'zone_low':      cl * (1 - sl_pct),
        'formed_bar':    len(df) - 1,
        'quality_score': 4,
        'quality_tags':  f'EMA200,EMA50,RSI50~65,Mom20b>3%',
        'ema200':        round(ema200, 2),
        'ema50':         round(ema50, 2),
        'rsi':           round(rsi, 1),
        'bb1_lower':     round(float(last.get('bb1_lower', 0)), 2),
        'bb_mid':        round(float(last.get('bb_mid', 0)), 2),
    }


# ── US 종목별 전략 신호 감지 함수 ────────────────────────────────────────
# 종목별 확정 전략 매핑 (2026-04-29):
#   NVDA, TSLA         → MACD 골든크로스
#   AMD                → BB반등 (BB하단 1% 이내 + RSI < 35)
#   MU, AVGO           → SuperTrend 돌파
#   GOOGL, AMZN, SHOP,
#   LRCX, MSTR         → BB반등+Momentum (BB하단 1% 이내 + RSI < 40 + 20봉 수익률 > 0)
# FVG+OB 신호가 없어도 이 전략이 발동되면 tradeable 신호로 반환

# 종목 → 전략 매핑 (scan_all 에서 참조)
# 전략 추가 방법: _US_STRATEGY_FN 과 _US_TICKER_STRATEGY 두 곳에만 추가하면 자동 연결됨
_US_STRATEGY_FN: dict[str, object] = {}   # 아래 함수 정의 후 채워짐

_US_TICKER_STRATEGY: dict[str, str] = {
    'NVDA': 'MACD',
    'TSLA': 'MACD',
    'AMD':  'BB_REVERSAL',
    'MU':   'SUPERTREND',
    'AVGO': 'SUPERTREND',
    'GOOGL': 'BB_MOM',
    'AMZN':  'BB_MOM',
    'SHOP':  'BB_MOM',
    'LRCX':  'BB_MOM',
    'MSTR':  'BB_MOM',
}


def _check_macd_signal(df: pd.DataFrame, market: str = 'US') -> dict | None:
    """MACD 골든크로스 신호 (일봉 기준).

    조건 (AND):
      1. MACD > Signal  (현재봉)
      2. MACD <= Signal (직전봉)  — 이번 봉에서 교차 발생
      3. Close > EMA200  (장기 상승 추세)

    SL/TP: 1% SL / 2% TP (US 기본값)

    Args:
        df: OHLCV 일봉 DataFrame (최소 220행).
        market: 시장 코드 ('US').

    Returns:
        신호 dict 또는 None.
    """
    if len(df) < 40:
        return None

    df = df.copy()
    c = df['Close']

    # EMA200
    ema200 = c.ewm(span=200, adjust=False).mean()
    cl = float(c.iloc[-1])
    if pd.isna(ema200.iloc[-1]) or cl < float(ema200.iloc[-1]):
        return None

    # MACD: EMA12 - EMA26, Signal: EMA9 of MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()

    if len(macd) < 2:
        return None

    macd_cur  = float(macd.iloc[-1])
    macd_prev = float(macd.iloc[-2])
    sig_cur   = float(signal_line.iloc[-1])
    sig_prev  = float(signal_line.iloc[-2])

    if pd.isna(macd_cur) or pd.isna(sig_cur):
        return None

    # 골든크로스: 현재봉 MACD > Signal AND 직전봉 MACD <= Signal
    if not (macd_cur > sig_cur and macd_prev <= sig_prev):
        return None

    sl_pct = SL_BY_MARKET.get(market, FIXED_SL_PCT)
    rr     = RR_BY_MARKET.get(market, 2.0)
    tp_pct = sl_pct * rr

    return {
        'type':          'MACD',
        'signal_type':   'MACD',
        'timeframe':     'daily',
        'entry':         round(cl, 4),
        'sl':            round(cl * (1 - sl_pct), 4),
        'tp':            round(cl * (1 + tp_pct), 4),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl,
        'zone_low':      cl * (1 - sl_pct),
        'formed_bar':    len(df) - 1,
        'quality_score': 3,
        'quality_tags':  f'EMA200,MACD_GoldenCross,macd={macd_cur:.4f},sig={sig_cur:.4f}',
        'ema200':        round(float(ema200.iloc[-1]), 2),
        'rsi':           float('nan'),
        'bb1_lower':     float('nan'),
        'bb_mid':        float('nan'),
    }


def _check_bb_reversal_signal(
    df: pd.DataFrame,
    rsi_threshold: float = 35.0,
    market: str = 'US',
) -> dict | None:
    """BB 하단 반등 신호 (일봉 기준) — AMD 전용.

    조건 (AND):
      1. Close <= BB 하단(2σ) × 1.01  (BB 하단 1% 이내)
      2. RSI(14) < rsi_threshold
      3. Close > EMA200

    SL/TP: 1% SL / 2% TP

    Args:
        df: OHLCV 일봉 DataFrame (최소 220행).
        rsi_threshold: RSI 상한 기준 (AMD=35, BB_MOM=40).
        market: 시장 코드.

    Returns:
        신호 dict 또는 None.
    """
    if len(df) < 40:
        return None

    df = _add_swing_indicators(df)
    last = df.iloc[-1]

    cl     = float(last['Close'])
    ema200 = float(last['ema200'])
    bb2_lo = float(last['bb2_lower'])
    rsi    = float(last['rsi'])
    bb_mid = float(last['bb_mid'])

    if any(pd.isna(v) for v in [ema200, bb2_lo, rsi]):
        return None

    # 1) EMA200 위
    if cl < ema200:
        return None

    # 2) BB 하단 1% 이내
    if cl > bb2_lo * 1.01:
        return None

    # 3) RSI 기준 미만
    if rsi >= rsi_threshold:
        return None

    sl_pct = SL_BY_MARKET.get(market, FIXED_SL_PCT)
    rr     = RR_BY_MARKET.get(market, 2.0)
    tp_pct = sl_pct * rr

    return {
        'type':          'BB_REVERSAL',
        'signal_type':   'BB_REVERSAL',
        'timeframe':     'daily',
        'entry':         round(cl, 4),
        'sl':            round(cl * (1 - sl_pct), 4),
        'tp':            round(cl * (1 + tp_pct), 4),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl,
        'zone_low':      cl * (1 - sl_pct),
        'formed_bar':    len(df) - 1,
        'quality_score': 3,
        'quality_tags':  (f'EMA200,BB2_Lower,RSI<{rsi_threshold:.0f},'
                          f'bb2_lo={bb2_lo:.4f},rsi={rsi:.1f}'),
        'ema200':        round(ema200, 2),
        'rsi':           round(rsi, 1),
        'bb1_lower':     round(float(last['bb1_lower']), 2),
        'bb_mid':        round(bb_mid, 2),
    }


def _check_supertrend_signal(df: pd.DataFrame, market: str = 'US') -> dict | None:
    """SuperTrend 돌파 신호 (일봉 기준) — MU, AVGO 전용.

    SuperTrend 파라미터: ATR(10), 배수 3.0
    조건: 현재봉 Close > SuperTrend 선 AND 직전봉 Close <= SuperTrend 선
          (하락 → 상승 전환, 즉 SuperTrend 돌파)

    SL: SuperTrend 선 기준 (최소 1% floor)
    TP: SL × RR

    Args:
        df: OHLCV 일봉 DataFrame (최소 30행).
        market: 시장 코드.

    Returns:
        신호 dict 또는 None.
    """
    if len(df) < 30:
        return None

    df = df.copy()
    atr_period = 10
    multiplier = 3.0

    # ATR 계산
    high = df['High']
    low  = df['Low']
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=atr_period, adjust=False).mean()

    # SuperTrend 상/하 밴드
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    # SuperTrend 방향 계산 (1=상승, -1=하락)
    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        prev_st  = supertrend.iloc[i - 1] if i > 1 else lower_band.iloc[i]
        prev_dir = direction.iloc[i - 1]  if i > 1 else 1
        cl_prev  = float(df['Close'].iloc[i - 1])
        cl_cur   = float(df['Close'].iloc[i])

        # 하단밴드 업데이트 (하락 중 밴드 끌어올리지 않음)
        lb = float(lower_band.iloc[i])
        ub = float(upper_band.iloc[i])
        lb_prev = float(lower_band.iloc[i - 1])
        ub_prev = float(upper_band.iloc[i - 1])

        lb = lb if lb > lb_prev or cl_prev < lb_prev else lb_prev
        ub = ub if ub < ub_prev or cl_prev > ub_prev else ub_prev

        if prev_dir == 1:
            if cl_cur < lb:
                direction.iloc[i] = -1
                supertrend.iloc[i] = ub
            else:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lb
        else:
            if cl_cur > ub:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lb
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = ub

    if len(supertrend.dropna()) < 2:
        return None

    cl_cur  = float(df['Close'].iloc[-1])
    cl_prev = float(df['Close'].iloc[-2])
    st_cur  = float(supertrend.iloc[-1])
    st_prev = float(supertrend.iloc[-2])
    dir_cur = int(direction.iloc[-1])

    if pd.isna(st_cur) or pd.isna(st_prev):
        return None

    # 돌파: 현재봉 상승 방향 전환 (직전 하락 → 현재 상승)
    if not (dir_cur == 1 and int(direction.iloc[-2]) == -1):
        return None

    # SL: SuperTrend 선 아래 (최소 1% floor)
    sl_floor = SL_BY_MARKET.get(market, FIXED_SL_PCT)
    st_sl_pct = (cl_cur - st_cur) / cl_cur if cl_cur > 0 else sl_floor
    sl_pct   = max(st_sl_pct, sl_floor)
    sl_pct   = min(sl_pct, SWING_SL_CAP)
    rr       = RR_BY_MARKET.get(market, 2.0)
    tp_pct   = sl_pct * rr

    return {
        'type':          'SUPERTREND',
        'signal_type':   'SUPERTREND',
        'timeframe':     'daily',
        'entry':         round(cl_cur, 4),
        'sl':            round(cl_cur * (1 - sl_pct), 4),
        'tp':            round(cl_cur * (1 + tp_pct), 4),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl_cur,
        'zone_low':      round(st_cur, 4),
        'formed_bar':    len(df) - 1,
        'quality_score': 3,
        'quality_tags':  f'SuperTrend_Breakout,st={st_cur:.4f},dir_prev=-1→1',
        'ema200':        float('nan'),
        'rsi':           float('nan'),
        'bb1_lower':     float('nan'),
        'bb_mid':        float('nan'),
    }


def _check_bb_mom_signal(df: pd.DataFrame, market: str = 'US') -> dict | None:
    """BB 반등 + Momentum 신호 (일봉 기준) — GOOGL/AMZN/SHOP/LRCX/MSTR 전용.

    조건 (AND):
      1. Close <= BB 하단(2σ) × 1.01
      2. RSI(14) < 40
      3. 20봉 수익률 > 0  (중기 모멘텀 양수)
      4. Close > EMA200

    SL/TP: 1% SL / 2% TP

    Args:
        df: OHLCV 일봉 DataFrame (최소 220행).
        market: 시장 코드.

    Returns:
        신호 dict 또는 None.
    """
    if len(df) < 40:
        return None

    df = _add_swing_indicators(df)
    last = df.iloc[-1]

    cl     = float(last['Close'])
    ema200 = float(last['ema200'])
    bb2_lo = float(last['bb2_lower'])
    rsi    = float(last['rsi'])
    bb_mid = float(last['bb_mid'])

    if any(pd.isna(v) for v in [ema200, bb2_lo, rsi]):
        return None

    # 1) EMA200 위
    if cl < ema200:
        return None

    # 2) BB 하단 1% 이내
    if cl > bb2_lo * 1.01:
        return None

    # 3) RSI < 40
    if rsi >= 40.0:
        return None

    # 4) 20봉 수익률 > 0
    if len(df) < 21:
        return None
    cl_20 = float(df['Close'].iloc[-21])
    if cl_20 <= 0 or (cl - cl_20) / cl_20 <= 0:
        return None

    sl_pct = SL_BY_MARKET.get(market, FIXED_SL_PCT)
    rr     = RR_BY_MARKET.get(market, 2.0)
    tp_pct = sl_pct * rr
    mom20  = (cl - cl_20) / cl_20 * 100

    return {
        'type':          'BB_MOM',
        'signal_type':   'BB_MOM',
        'timeframe':     'daily',
        'entry':         round(cl, 4),
        'sl':            round(cl * (1 - sl_pct), 4),
        'tp':            round(cl * (1 + tp_pct), 4),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl,
        'zone_low':      cl * (1 - sl_pct),
        'formed_bar':    len(df) - 1,
        'quality_score': 3,
        'quality_tags':  (f'EMA200,BB2_Lower,RSI<40,Mom20b>0,'
                          f'bb2_lo={bb2_lo:.4f},rsi={rsi:.1f},mom20={mom20:.2f}%'),
        'ema200':        round(ema200, 2),
        'rsi':           round(rsi, 1),
        'bb1_lower':     round(float(last['bb1_lower']), 2),
        'bb_mid':        round(bb_mid, 2),
    }


# ── US 전략 레지스트리 채우기 (함수 정의 완료 후) ─────────────────────────────
# 새 전략 추가 시 여기에만 한 줄 추가 → 디스패처 자동 반영
_US_STRATEGY_FN.update({
    'MACD':        lambda df: _check_macd_signal(df, market='US'),
    'BB_REVERSAL': lambda df: _check_bb_reversal_signal(df, rsi_threshold=35.0, market='US'),
    'SUPERTREND':  lambda df: _check_supertrend_signal(df, market='US'),
    'BB_MOM':      lambda df: _check_bb_mom_signal(df, market='US'),
    'BB_SWING':    lambda df: _check_swing_signal(df, market='US'),
})


def _check_us_ticker_strategy(
    code: str,
    df: pd.DataFrame,
) -> dict | None:
    """US 종목별 확정 전략 신호 감지.

    _US_TICKER_STRATEGY 매핑 → _US_STRATEGY_FN 레지스트리 순으로 조회.
    두 딕셔너리에만 추가하면 여기 코드는 수정 불필요.

    Args:
        code: 종목 코드 (예: 'NVDA').
        df: 일봉 OHLCV DataFrame.

    Returns:
        신호 dict (signal_type 필드 포함) 또는 None.
    """
    strategy = _US_TICKER_STRATEGY.get(code)
    if strategy is None:
        return None
    fn = _US_STRATEGY_FN.get(strategy)
    if fn is None:
        print(f"  [경고] US 전략 '{strategy}' 가 레지스트리에 없음 — _US_STRATEGY_FN 에 추가 필요")
        return None
    return fn(df)


# ── KR 종목별 전략 신호 감지 함수 ───────────────────────────────────────────
# 전략 추가 방법: 아래 두 딕셔너리에만 추가하면 자동 연결됨.
# _KR_STRATEGY_FN: 전략명 → 함수 (lambda로 market 고정)
# _KR_TICKER_STRATEGY: 종목코드 → 전략명
#
# 예) 신전략 추가:
#   _KR_STRATEGY_FN['MY_STRAT'] = lambda df: _check_my_signal(df, market='KR')
#   _KR_TICKER_STRATEGY['012345'] = 'MY_STRAT'

# 전략명 → 함수 레지스트리 (이곳만 수정하면 디스패처 자동 반영)
_KR_STRATEGY_FN: dict[str, object] = {}   # 아래에서 채워짐 (함수 정의 후)

_KR_TICKER_STRATEGY: dict[str, str] = {
    # ── 확정 전략 배정 (2026-04-30 V4.6 완성) ──
    # 백테스트 WR 기준 최적 전략 배정
    # 특수 전략 4종목
    '010140': 'SUPERTREND',   # 삼성중공업 WR75.0% — SuperTrend 돌파
    '086790': 'MACD',         # 하나금융   WR73.3% — MACD 골든크로스
    '272210': 'GAPGO',        # 한화시스템 WR60.0% — 갭업 돌파
    '005930': 'MOMENTUM',     # 삼성전자   WR56.5% — Momentum (EMA200+EMA50+RSI50~65)
    # BB_SWING 전략 12종목 (WR 기준 정렬)
    '017670': 'BB_SWING',     # SK텔레콤   WR85.7%
    '035720': 'BB_SWING',     # 카카오     WR81.8%
    '021240': 'BB_SWING',     # 코웨이     WR78.6%
    '005380': 'BB_SWING',     # 현대차     WR77.8%
    '034020': 'BB_SWING',     # 두산에너빌 WR66.7%
    '009150': 'BB_SWING',     # 삼성전기   WR52.9%
    '000660': 'BB_SWING',     # SK하이닉스 WR55.1%
    '008060': 'BB_SWING',     # 대덕전자   WR56.5%
    '058470': 'BB_SWING',     # 리노공업   WR51.7%
    '064350': 'BB_SWING',     # 현대로템   WR48.4%
    '128940': 'BB_SWING',     # 한미약품   WR44.2%
    '012450': 'BB_SWING',     # 한화에어로 WR43.7%
}


def _check_gapgo_signal(df: pd.DataFrame, market: str = 'KR') -> dict | None:
    """갭업 돌파 신호 (일봉 기준) — 한화시스템(272210) 전용.

    조건 (AND):
      1. 오늘 Open > 전일 Close × 1.005  (0.5% 이상 갭업)
      2. Close > Open  (갭업 유지, 양봉)
      3. 거래량 > 20일 평균 거래량 × 1.3  (거래량 급증)
      4. RSI(14) > 50  (모멘텀 확인)
      5. Close > EMA200  (장기 상승 추세)

    SL: 오늘 Open 아래 (최소 2% floor, KR 기준)
    TP: SL × R:R 2.0

    Args:
        df: OHLCV 일봉 DataFrame (최소 220행).
        market: 시장 코드 ('KR').

    Returns:
        신호 dict 또는 None.
    """
    if len(df) < 30:
        return None

    df = df.copy()
    c   = df['Close']
    o   = df['Open']
    v   = df['Volume']

    cl      = float(c.iloc[-1])
    op      = float(o.iloc[-1])
    cl_prev = float(c.iloc[-2])

    # EMA200
    ema200 = float(c.ewm(span=200, adjust=False).mean().iloc[-1])
    if cl < ema200:
        return None

    # RSI(14)
    delta  = c.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    rs     = gain / loss.replace(0, float('nan'))
    rsi    = float((100 - 100 / (1 + rs)).iloc[-1])

    # 조건 1: 갭업
    if op <= cl_prev * 1.005:
        return None
    # 조건 2: 양봉
    if cl <= op:
        return None
    # 조건 3: 거래량
    vol_avg = float(v.iloc[-21:-1].mean())
    if vol_avg > 0 and float(v.iloc[-1]) < vol_avg * 1.3:
        return None
    # 조건 4: RSI
    if pd.isna(rsi) or rsi <= 50.0:
        return None

    sl_floor = SL_BY_MARKET.get(market, FIXED_SL_PCT)
    gap_sl   = (cl - op) / cl if cl > 0 else sl_floor
    sl_pct   = max(gap_sl, sl_floor)
    sl_pct   = min(sl_pct, SWING_SL_CAP)
    rr       = RR_BY_MARKET.get(market, 2.0)
    tp_pct   = sl_pct * rr
    gap_pct  = (op - cl_prev) / cl_prev * 100

    return {
        'type':          'GAPGO',
        'signal_type':   'GAPGO',
        'timeframe':     'daily',
        'entry':         round(cl, 0),
        'sl':            round(cl * (1 - sl_pct), 0),
        'tp':            round(cl * (1 + tp_pct), 0),
        'sl_pct':        round(-sl_pct * 100, 2),
        'tp_pct':        round(tp_pct * 100, 2),
        'zone_high':     cl,
        'zone_low':      round(op, 0),
        'formed_bar':    len(df) - 1,
        'quality_score': 3,
        'quality_tags':  (f'GapUp={gap_pct:.2f}%,BullCandle,VolSpike,RSI>{rsi:.0f},EMA200'),
        'ema200':        round(ema200, 0),
        'rsi':           round(rsi, 1),
        'bb1_lower':     float('nan'),
        'bb_mid':        float('nan'),
    }


# ── 전략 레지스트리 채우기 (함수 정의 완료 후) ──────────────────────────────
# 새 전략 추가 시 여기에만 한 줄 추가 → 디스패처 자동 반영
_KR_STRATEGY_FN.update({
    'BB_SWING':   lambda df: _check_swing_signal(df, market='KR'),
    'MACD':       lambda df: _check_macd_signal(df, market='KR'),
    'SUPERTREND': lambda df: _check_supertrend_signal(df, market='KR'),
    'GAPGO':      lambda df: _check_gapgo_signal(df, market='KR'),
    'MOMENTUM':   lambda df: _check_momentum_signal(df, market='KR'),
})


def _check_kr_ticker_strategy(
    code: str,
    df: pd.DataFrame,
) -> dict | None:
    """KR 종목별 확정 전략 신호 감지.

    _KR_TICKER_STRATEGY 매핑 → _KR_STRATEGY_FN 레지스트리 순으로 조회.
    두 딕셔너리에만 추가하면 여기 코드는 수정 불필요.

    Args:
        code: 종목 코드 (예: '010140').
        df: 일봉 OHLCV DataFrame.

    Returns:
        신호 dict (signal_type 필드 포함) 또는 None.
    """
    strategy = _KR_TICKER_STRATEGY.get(code)
    if strategy is None:
        return None
    fn = _KR_STRATEGY_FN.get(strategy)
    if fn is None:
        print(f"  [경고] KR 전략 '{strategy}' 가 레지스트리에 없음 — _KR_STRATEGY_FN 에 추가 필요")
        return None
    return fn(df)


def _load(yf_ticker: str, interval: str = '15m') -> pd.DataFrame | None:
    """OHLCV 로드 — v8 API 우선, yf.download fallback"""
    # v8 API 유효 range: 1d/5d/1mo/3mo/6mo/1y/2y/5y/ytd/max
    range_map = {
        '1m': '1d', '5m': '5d', '15m': '5d',
        '1h': '3mo', '4h': '3mo', '1d': '1y',
    }
    range_str = range_map.get(interval, '5d')
    # v8 API 직접 호출 (yfinance 1.3.0 호환성 문제 우회)
    df = _yahoo_fetch(yf_ticker, interval, range_str)
    if df is not None and len(df) >= 10:
        return df
    # fallback: yf.download
    try:
        period = '60d' if interval in ('1h',) else '5d'
        df2 = yf.download(yf_ticker, period=period, interval=interval,
                          auto_adjust=True, progress=False)
        if df2 is None or df2.empty: return None
        if hasattr(df2.columns, 'levels'): df2.columns = df2.columns.droplevel(1)
        if df2.index.tz is not None: df2.index = df2.index.tz_localize(None)
        return df2[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return None


def _load_5m_kr(code: str) -> pd.DataFrame | None:
    """KR 종목 5분봉 로드: KIS API 우선, 실패 시 yfinance 폴백"""
    df = None
    try:
        from core.kis_trader import get_ohlcv_5m as _kis_5m
        df = _kis_5m(code)
    except Exception:
        pass
    if df is None or len(df) < 10:
        yf_tk = KR_TICKERS.get(code, (None, f'{code}.KS', '15m'))[1]
        df = _load(yf_tk, '5m')
    return df



def _check_15m_filters(yf_tk: str, sig: dict) -> dict | None:
    """
    15m 보조 필터 3종 (2026-04-29 추가) — Daily/4H 신호의 진입 품질 향상
    [Filter 1] EMA5 > EMA20 정렬: 15m 단기 상승 추세 확인
    [Filter 2] CHoCH 근사: 최근 3봉 스윙로우가 상승 중 (구조 전환)
    [Filter 3] SL 정밀화: 15m 직전 스윙로우로 SL 교체 (손실 축소)
    반환: 필터 통과 시 SL 업데이트된 sig dict, 실패 시 None
    """
    try:
        df15 = _load(yf_tk, '15m')
        if df15 is None or len(df15) < 30:
            return sig  # 데이터 없으면 통과 (안전 fallback)

        df15 = df15.copy()
        df15['ema5']  = df15['Close'].ewm(span=5,  adjust=False).mean()
        df15['ema20'] = df15['Close'].ewm(span=20, adjust=False).mean()

        last = df15.iloc[-1]
        ema5  = float(last['ema5'])
        ema20 = float(last['ema20'])
        cl    = float(last['Close'])

        # [Filter 1] EMA5 > EMA20 정렬
        if ema5 <= ema20:
            return None  # 15m 하락 추세 → 진입 차단

        # [Filter 2] CHoCH 근사: 최근 3개 스윙로우(5봉 기준) 상승 중?
        lows = []
        lookback = min(len(df15) - 1, 30)
        for i in range(lookback, 4, -1):
            window = df15['Low'].iloc[i-4:i+1]
            if float(df15['Low'].iloc[i]) == float(window.min()):
                lows.append(float(df15['Low'].iloc[i]))
            if len(lows) >= 3:
                break
        if len(lows) >= 2 and lows[0] <= lows[1]:
            return None  # 스윙로우 하락 중 → 구조 전환 미확인

        # [Filter 3] SL 정밀화: 15m 직전 스윙로우로 SL 교체
        swing_low = float(df15['Low'].iloc[-10:].min())
        entry = sig['entry']
        new_sl_pct = (entry - swing_low) / entry
        # 너무 타이트(0.3% 미만)하거나 너무 넓으면(3% 초과) 원본 유지
        if 0.003 <= new_sl_pct <= 0.03:
            rr = 2.0
            sig = dict(sig)
            sig['sl']     = round(swing_low, 4)
            sig['sl_pct'] = round(-new_sl_pct * 100, 2)
            sig['tp']     = round(entry * (1 + new_sl_pct * rr), 4)
            sig['tp_pct'] = round(new_sl_pct * rr * 100, 2)
            sig['quality_tags'] = sig.get('quality_tags','') + ',15mEMA,15mCHoCH,15mSL'

        return sig
    except Exception:
        return sig  # 오류 시 통과 (안전 fallback)

def _check_5m_confirm(df5: pd.DataFrame | None, zone_low: float, zone_high: float) -> bool:
    """
    5분봉 확인 캔들 체크 (2026-04-28 추가)
    조건: 최근 5m 봉이 FVG/OB 존 내부에서 양봉(Close > Open)으로 마감
    → True이면 진입 허용, False이면 보류
    """
    if df5 is None or len(df5) < 2:
        return True  # 데이터 없으면 통과 (안전 fallback)
    last = df5.iloc[-1]
    op  = float(last['Open'])
    cl  = float(last['Close'])
    lo  = float(last['Low'])
    # 양봉 조건 + 저점이 존 아래로 벗어나지 않은 조건
    is_bullish = cl > op
    in_zone    = lo <= zone_high and cl >= zone_low
    return is_bullish and in_zone


def _check_htf_weekly(df_1h: pd.DataFrame) -> bool:
    """
    주봉 HTF 필터 (2026-04-28 추가)
    1H 데이터를 주봉으로 리샘플 후 EMA20 위인지 확인
    → True: 주봉 상승추세 (진입 허용)
    → False: 주봉 하락추세 (진입 차단)
    근거: CRYPTO 4H 백테스트 HTF 적용 시 XRP WR +16.1%p 개선
    """
    if df_1h is None or len(df_1h) < 200:
        return True  # 데이터 부족 시 통과 (안전 fallback)
    try:
        dfw = df_1h.resample('W').agg({
            'Open': 'first', 'High': 'max',
            'Low': 'min', 'Close': 'last',
        }).dropna()
        if len(dfw) < 22:
            return True
        ema20w = float(dfw['Close'].ewm(span=20, adjust=False).mean().iloc[-1])
        last_close = float(dfw['Close'].iloc[-1])
        return last_close > ema20w
    except Exception:
        return True  # 오류 시 통과


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
    진입 품질 11가지 기준으로 점수 계산 (0~11)
    점수가 높을수록 진짜 진입(Real). MIN_ENTRY_QUALITY 미만은 Fake로 간주.

    기존 7점:
    1) RSI < 65          (과매수 아님)
    2) Volume 확인        (현재봉 > 20봉 평균)
    3) EMA 정배열         (9 > 21 > 50)
    4) 구간 첫 접촉       (신선한 구간)
    5) 핀바/해머 구조     (긴 아래꼬리)
    6) VWAP 위
    7) 직전 스윙로우 위

    신규 4점 (Real vs Fake 핵심 필터):
    8)  Volume Spike      (평균의 1.5배 이상 = 기관 개입 확인)
    9)  Liquidity Sweep   (직전 스윙로우 잠깐 돌파 후 복귀 = Fake 털고 Real 진입)
    10) CHoCH             (하락 구조 중 이전 고점 돌파 = 구조 전환)
    11) Body Close in Zone (캔들 몸통이 구간 안에서 마감 = 진짜 반전)
    """
    if len(df) < 30:
        return 0, []

    c   = df['Close']
    scores: list[str] = []

    # ── 기존 7점 ─────────────────────────────────────────────────

    # 1) RSI 과매수 아님
    d = c.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    rsi = (100 - 100 / (1 + g / l.replace(0, float('nan')))).iloc[-1]
    if not float('nan') == rsi and rsi < 65:
        scores.append('RSI<65')

    # 2) 거래량 확인 (Volume > 20봉 평균 × 0.8)
    vol = df['Volume']
    avg_vol = vol.rolling(20).mean().iloc[-1] if len(vol) >= 20 else vol.mean()
    if vol.sum() > 0 and avg_vol > 0 and vol.iloc[-1] > avg_vol * 0.8:
        scores.append('Vol_OK')

    # 3) EMA 정배열
    e9  = c.ewm(span=9,  adjust=False).mean().iloc[-1]
    e21 = c.ewm(span=21, adjust=False).mean().iloc[-1]
    e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    if e9 > e21 > e50:
        scores.append('EMA_Align')

    # 4) 구간 신선도 (최근 10봉 접촉 1회 이하)
    recent_lows = df['Low'].tail(10).values
    touches = sum(1 for lo in recent_lows[:-1] if zone_low * 0.995 <= lo <= zone_low * 1.02)
    if touches <= 1:
        scores.append('Fresh_Zone')

    # 5) 핀바/해머 (긴 아래꼬리 = 매수 압력)
    bar = df.iloc[-1]
    body = abs(float(bar['Close']) - float(bar['Open']))
    lower_wick = float(min(bar['Open'], bar['Close'])) - float(bar['Low'])
    candle_range = float(bar['High']) - float(bar['Low'])
    if candle_range > 0 and lower_wick > body and lower_wick / candle_range > 0.35:
        scores.append('PinBar')

    # 6) VWAP 위
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vol_s = df['Volume'].replace(0, float('nan'))
    vwap = (tp * vol_s).cumsum() / vol_s.cumsum()
    if not pd.isna(vwap.iloc[-1]) and float(c.iloc[-1]) >= float(vwap.iloc[-1]) * 0.998:
        scores.append('Above_VWAP')

    # 7) 직전 스윙로우 위
    swing_low = float(df['Low'].tail(10).iloc[:-1].min())
    if entry > swing_low * 0.998:
        scores.append('Above_SwingLow')

    # ── 신규 4점: Real vs Fake 핵심 필터 ─────────────────────────

    # 8) Volume Spike — 기관 개입 확인 (평균의 1.5배 이상)
    if vol.sum() > 0 and avg_vol > 0 and vol.iloc[-1] > avg_vol * 1.5:
        scores.append('Vol_Spike')

    # 9) Liquidity Sweep — 직전 스윙로우 잠깐 돌파 후 복귀
    #    최근 5봉 중 Low가 swing_low 아래로 갔다가 현재 Close가 swing_low 위로 복귀
    if len(df) >= 10:
        recent5_lows = df['Low'].tail(5).values
        swept = any(lo < swing_low * 0.999 for lo in recent5_lows[:-1])
        recovered = float(c.iloc[-1]) > swing_low
        if swept and recovered:
            scores.append('Liq_Sweep')

    # 10) CHoCH — 하락 구조 중 이전 고점 돌파 (구조 전환)
    #     최근 10봉 고점을 현재 Close가 돌파
    if len(df) >= 15:
        prev_highs = df['High'].tail(15).iloc[:-3]  # 최근 3봉 제외한 고점들
        recent_high = float(prev_highs.max())
        # 직전 구조가 하락 (최근 5봉 평균 < 10봉 전 평균)
        was_downtrend = float(c.tail(5).mean()) < float(c.tail(15).head(5).mean())
        if was_downtrend and float(c.iloc[-1]) > recent_high * 0.998:
            scores.append('CHoCH')

    # 11) Body Close in Zone — 캔들 몸통이 구간 안에서 마감 (진짜 반전)
    #     Fake는 위꼬리만 구간 진입 후 몸통은 구간 밖, Real은 몸통이 구간 안
    bar_close = float(bar['Close'])
    bar_open  = float(bar['Open'])
    body_low  = min(bar_close, bar_open)
    zone_high = zone_low * 1.015  # 구간 상단 추정
    if body_low >= zone_low * 0.998 and bar_close >= zone_low:
        scores.append('Body_In_Zone')

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

            # ── 1순위 진입 신중 필터 (2026-04-28 적용) ───────────────
            # Vol_Spike + Body_In_Zone 동시 만족해야 진입
            # → 기관 개입 확인 + 몸통이 존 안에서 마감 (Fake 캔들 제거)
            quality_score, quality_tags = _entry_quality_score(df, entry, zl)
            has_vol_spike    = 'Vol_Spike'    in quality_tags
            has_body_in_zone = 'Body_In_Zone' in quality_tags

            if not (has_vol_spike and has_body_in_zone):
                continue  # 둘 다 없으면 스킵 (Fake 진입 차단)

            # ── 2순위: Close가 존 상단 50% 이상 (확인 캔들 대체) ─────
            # 존에 살짝 걸친 게 아니라 존 중간 이상에서 양봉 마감 확인
            zone_mid = zl + (zh - zl) * 0.5
            if cl < zone_mid:
                continue  # 존 하단부에서만 걸친 경우 스킵

            # SL: 구조적 존 거리와 최솟값(0.5%) 중 큰 값 사용 (floor)
            zone_sl_pct = (entry - zl) / entry if entry > 0 else FIXED_SL_PCT
            sl_pct = max(zone_sl_pct, FIXED_SL_PCT)
            if sl_pct > MAX_SL_PCT:
                continue  # 존이 너무 넓으면 스킵
            sl = entry * (1 - sl_pct)
            tp = entry * (1 + sl_pct * RR_RATIO)  # TP = SL × 2, 최소 1.0%

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


def _check_signal_with_quality(
    df: pd.DataFrame,
    min_q: int,
    ticker_code: str = '',
    market: str = '',
) -> dict | None:
    """
    min_q 품질 기준 + (옵션) 5m 확인 캔들 필터 적용한 신호 체크 래퍼

    USE_5M_CONFIRM = True  → KR 종목은 5m 확인 캔들 통과해야 진입
    USE_5M_CONFIRM = False → 기존 15m 방식 그대로 (기본값)
    A/B 비교: sig에 '5m_confirm' 필드 추가 → 성과 분석 가능
    """
    sig = _check_signal(df)
    if sig is None:
        return None
    if min_q > 0 and sig.get('quality_score', 0) < min_q:
        return None

    # ── 5분봉 확인 캔들 (KR + CRYPTO 적용, US는 장 시간대 짧아 선택적) ──
    confirm_5m = None   # None = 미확인, True = 통과, False = 실패
    zh = sig.get('zone_high', 0)
    zl = sig.get('zone_low', 0)

    if ticker_code and market == 'KR':
        df5 = _load_5m_kr(ticker_code)
        confirm_5m = _check_5m_confirm(df5, zl, zh)

    elif ticker_code and market == 'CRYPTO':
        # CRYPTO: yfinance 5m 직접 사용 (BTC-USD, ETH-USD 등)
        yf_tk = CRYPTO_TICKERS.get(ticker_code, (None, ticker_code + '-USD', '15m'))[1]
        df5 = _load(yf_tk, '5m')
        confirm_5m = _check_5m_confirm(df5, zl, zh)

    sig['has_5m_confirm'] = confirm_5m

    if USE_5M_CONFIRM and market in ('KR', 'CRYPTO') and not confirm_5m:
        return None  # 5m 양봉 미확인 → 보류 (US는 해당없음)

    # ── 시장별 SL/TP/R:R 재계산 ────────────────────────────────────
    # CRYPTO: zone 기반 가변 SL (4H 백테스트 방식 복원, 2026-04-28)
    #   → 4H WR 61% / +400% 검증된 방식. 고정 SL보다 구조적으로 정확
    # KR/US:  1% floor SL / TP 2%
    if market:
        rr    = RR_BY_MARKET.get(market, RR_RATIO)
        entry = sig['entry']
        zone_low = sig.get('zone_low', entry * (1 - FIXED_SL_PCT))

        if market == 'CRYPTO':
            # zone 기반 가변 SL (floor 0.3%, 상한 3%)
            zone_sl_pct = (entry - zone_low) / entry if entry > 0 else 0.005
            sl_pct = max(zone_sl_pct, 0.003)   # 최소 0.3%
        else:
            # KR/US: 1% floor
            sl_floor = SL_BY_MARKET.get(market, FIXED_SL_PCT)
            zone_sl_pct = (entry - zone_low) / entry if entry > 0 else sl_floor
            sl_pct = max(zone_sl_pct, sl_floor)

        if sl_pct > MAX_SL_PCT:
            return None   # 존이 너무 넓으면 스킵
        sl = entry * (1 - sl_pct)
        tp = entry * (1 + sl_pct * rr)
        sig['sl']     = round(sl, 4)
        sig['tp']     = round(tp, 4)
        sig['sl_pct'] = round(-sl_pct * 100, 2)
        sig['tp_pct'] = round(sl_pct * rr * 100, 2)

    return sig


def _rank_signal(sig: dict) -> float:
    """
    신호 종합 우선순위 점수 (높을수록 먼저 거래)
    구성:
      - quality_score (0~7)  × 2.0  → 최대 14점
      - 4H 타임프레임 보너스         → +5점  (백테스트 1위)
      - FVG 신호 우선 보너스         → +3점  (FVG WR 67% vs OB 39%, 2026-04-28 검증)
      - 코인 시장 보너스             → +2점  (백테스트 압도적 우위)
      - 구간 크기 (FVG/OB 강도)     → 최대 3점
      - TP 잠재력                    → 최대 2점
    """
    score = sig.get('quality_score', 0) * 2.0

    if sig.get('timeframe') == '4H':
        score += 5.0

    # FVG 우선 랭킹 (2026-04-28 적용: FVG WR 67% vs OB WR 39%)
    if sig.get('type') == 'FVG':
        score += 3.0

    if sig.get('market') == 'CRYPTO':
        score += 2.0

    # 구간 크기 — 클수록 강한 불균형
    gap_pct = (sig['zone_high'] - sig['zone_low']) / max(sig['zone_low'], 1e-9) * 100
    score += min(gap_pct * 5, 3.0)

    # TP 잠재력
    score += min(sig.get('tp_pct', 0) * 0.4, 2.0)

    return score


def scan_all() -> list:
    """전 종목 FVG+OB 신호 스캔 (KR5 + US5 + CRYPTO4)
    Pillar 1 매크로 국면에 따라 자동으로 필터 강도 조절
    """
    signals = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ── Pillar 1: 매크로 국면 판단 ───────────────────────
    try:
        regime, macro_data = get_regime()
    except Exception:
        regime, macro_data = 'NORMAL', {}

    min_q = min_quality_by_regime(regime)

    print(f"\n{'='*65}")
    print(f"  FVG+OB Forward Scanner [{now_str}]")
    print(f"  KR 5종목 + US 5종목 + CRYPTO 4종목 (15분봉)")
    print(f"  Pillar1 Regime: [{regime}]  품질필터: {min_q}점 이상" +
          (f"  VIX={macro_data.get('vix','?'):.1f}" if macro_data.get('vix') else ""))
    print(f"{'='*65}\n")

    # HALT → 전면 차단
    if regime == 'HALT':
        print(f"  *** HALT: VIX={macro_data.get('vix','?')} 위기 수준 — 오늘 거래 없음 ***")
        return []

    # ── 한국주식 ────────────────────────────────────────────
    if SWING_MODE_KR:
        # 스윙 모드: 일봉 FVG+OB+DBB+EMA200
        print("  [한국주식 — 스윙 모드 (일봉)]")
        for code, (name, yf_tk) in KR_SWING_TICKERS.items():
            df = _load_daily(yf_tk)
            if df is None or len(df) < 220:
                print(f"    {name}({code}): 데이터 부족")
                continue
            price = _kr_current_price(code) or float(df['Close'].iloc[-1])

            # 종목별 확정 전략이 있으면 공통 BB반등+OB 차단, 해당 전략만 사용
            has_kr_strategy = code in _KR_TICKER_STRATEGY

            if has_kr_strategy:
                sig = None
                ticker_sig = _check_kr_ticker_strategy(code, df)
            else:
                sig = _check_swing_signal(df, market='KR') or _check_momentum_signal(df, market='KR')
                if sig:
                    sig = _check_15m_filters(yf_tk, sig)
                ticker_sig = None

            if sig:
                sig_label = f"{sig['type']}({'BB반등' if sig['type'] in ('FVG','OB') else 'Momentum'})"
                print(f"    *** {name}({code}) 스윙 | {sig_label} | "
                      f"현재가={price:,.0f} | SL={sig['sl_pct']:.1f}% | "
                      f"TP=+{sig['tp_pct']:.1f}% | RSI={sig.get('rsi', float('nan')):.0f}")
                signals.append({'ticker': code, 'name': name, 'market': 'KR',
                                'price': price, **sig})

            if ticker_sig is not None:
                strat_name = ticker_sig.get('signal_type', ticker_sig['type'])
                rsi_val = ticker_sig.get('rsi', float('nan'))
                rsi_str = f"{rsi_val:.0f}" if rsi_val == rsi_val else 'N/A'
                print(f"    *** {name}({code}) [{strat_name}] | "
                      f"현재가={price:,.0f} | SL={ticker_sig['sl_pct']:.1f}% | "
                      f"TP=+{ticker_sig['tp_pct']:.1f}% | RSI={rsi_str}")
                signals.append({'ticker': code, 'name': name, 'market': 'KR',
                                'price': price, **ticker_sig})

            if not sig and ticker_sig is None:
                try:
                    df2 = _add_swing_indicators(df)
                    last2 = df2.iloc[-1]
                    strat_hint = _KR_TICKER_STRATEGY.get(code, 'BB반등+OB')
                    print(f"    {name}({code}) [{strat_hint}] | 현재가={price:,.0f} | "
                          f"EMA200={float(last2['ema200']):,.0f} | "
                          f"BB1하단={float(last2['bb1_lower']):,.0f} | "
                          f"RSI={float(last2['rsi']):.0f} | 신호없음")
                except Exception:
                    print(f"    {name}({code}) | 현재가={price:,.0f} | 신호없음")
    else:
        # 15m 단타 모드 (비활성화 중)
        print("  [한국주식 — 15m 단타 비활성화]")
        for code, (name, yf_tk, interval) in KR_TICKERS.items():
            df = None
            try:
                from core.kis_trader import get_ohlcv_15m as _kis_ohlcv
                df = _kis_ohlcv(code)
            except Exception:
                pass
            if df is None or len(df) < 30:
                df = _load(yf_tk, interval)
            if df is None or len(df) < 30:
                print(f"    {name}({code}): 데이터 없음")
                continue
            price = None
            try:
                from core.kis_trader import get_price as _kis_price
                p = _kis_price(code)
                if p > 0:
                    price = float(p)
            except Exception:
                pass
            if not price:
                price = _kr_current_price(code) or float(df['Close'].iloc[-1])
            sig = _check_signal_with_quality(df, min_q, ticker_code=code, market='KR')
            if sig:
                signals.append({'ticker': code, 'name': name, 'market': 'KR',
                                'price': price, **sig})

    # ── 미국주식 ────────────────────────────────────────────
    if SWING_MODE_US:
        # 스윙 모드: 일봉 FVG+OB+DBB+EMA200 + 종목별 확정 전략
        print("\n  [미국주식 — 스윙 모드 (일봉)]")
        for code, (name, yf_tk) in US_SWING_TICKERS.items():
            df = _load_daily(yf_tk)
            if df is None or len(df) < 220:
                print(f"    {name}({code}): 데이터 부족")
                continue
            price = float(df['Close'].iloc[-1])

            # ── 종목별 확정 전략이 있으면 FVG+OB 차단, 해당 전략만 사용 ──
            has_ticker_strategy = code in _US_TICKER_STRATEGY

            if has_ticker_strategy:
                # NVDA/TSLA/AMD 등 종목별 전략 지정 종목: 오직 지정 전략만 사용
                sig = None
                ticker_sig = _check_us_ticker_strategy(code, df)
            else:
                # FVG+OB 적용 종목 (매핑 없는 종목)
                sig = _check_swing_signal(df, market='US') or _check_momentum_signal(df, market='US')
                if sig:
                    sig = _check_15m_filters(yf_tk, sig)
                ticker_sig = None

            if sig:
                sig_label = f"{sig['type']}({'BB반등' if sig['type'] in ('FVG','OB') else 'Momentum'})"
                print(f"    *** {name}({code}) 스윙 | {sig_label} | "
                      f"현재가={price:.2f} | SL={sig['sl_pct']:.1f}% | "
                      f"TP=+{sig['tp_pct']:.1f}% | RSI={sig.get('rsi', float('nan')):.0f}")
                signals.append({'ticker': code, 'name': name, 'market': 'US',
                                'price': price, **sig})

            if ticker_sig is not None:
                strat_name = ticker_sig.get('signal_type', ticker_sig['type'])
                rsi_val = ticker_sig.get('rsi', float('nan'))
                rsi_str = f"{rsi_val:.0f}" if rsi_val == rsi_val else 'N/A'
                print(f"    *** {name}({code}) [{strat_name}] | "
                      f"현재가={price:.2f} | SL={ticker_sig['sl_pct']:.1f}% | "
                      f"TP=+{ticker_sig['tp_pct']:.1f}% | RSI={rsi_str}")
                signals.append({'ticker': code, 'name': name, 'market': 'US',
                                'price': price, **ticker_sig})

            # ── 둘 다 없으면 디버그 출력 ──
            if not sig and ticker_sig is None:
                try:
                    df2 = _add_swing_indicators(df)
                    last2 = df2.iloc[-1]
                    strat_hint = _US_TICKER_STRATEGY.get(code, 'FVG+OB')
                    print(f"    {name}({code}) [{strat_hint}] | 현재가={price:.2f} | "
                          f"EMA200={float(last2['ema200']):.2f} | "
                          f"BB1하단={float(last2['bb1_lower']):.2f} | "
                          f"RSI={float(last2['rsi']):.0f} | 신호없음")
                except Exception:
                    print(f"    {name}({code}) | 현재가={price:.2f} | 신호없음")
    else:
        # 15m 단타 모드 (비활성화 중)
        print("\n  [미국주식 — 15m 단타 비활성화]")
        for code, (name, yf_tk, interval) in US_TICKERS.items():
            df = _load(yf_tk, interval)
            if df is None or len(df) < 30:
                print(f"    {name}({code}): 데이터 없음")
                continue
            price = float(df['Close'].iloc[-1])
            sig = _check_signal_with_quality(df, min_q, ticker_code=code, market='US')
            if sig:
                signals.append({'ticker': code, 'name': name, 'market': 'US',
                                'price': price, **sig})

    # ── 암호화폐 ────────────────────────────────────────────
    print("\n  [암호화폐]")
    for code, (name, yf_tk, interval) in CRYPTO_TICKERS.items():
        df = _load(yf_tk, interval)
        if df is None or len(df) < 30:
            print(f"    {name}({code}): 데이터 없음")
            continue
        price = float(df['Close'].iloc[-1])
        sig = _check_signal_with_quality(df, min_q, ticker_code=code, market='CRYPTO')
        if sig:
            print(f"    *** {name}({code}) | {sig['type']} 신호 | "
                  f"현재가={price:.2f} | 진입={sig['entry']:.2f} | "
                  f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
            signals.append({'ticker': code, 'name': name, 'market': 'CRYPTO',
                            'price': price, **sig})
        else:
            print(f"    {name}({code}) | 현재가={price:.2f} | 신호없음")

    # ── 4H 스캔 (백테스트 1위 타임프레임) ──────────────────────
    print("\n  [4H 스캔 — CRYPTO + US 핵심종목]")
    for group_name, tickers_4h in [('CRYPTO', CRYPTO_4H_TICKERS), ('US', US_4H_TICKERS)]:
        for code, (name, yf_tk) in tickers_4h.items():
            # 1h 데이터 다운로드 후 4h 리샘플
            df_1h = _load(yf_tk, '1h')
            if df_1h is None or len(df_1h) < 30:
                print(f"    {name}({code}) 4H: 데이터 없음")
                continue
            df = df_1h.resample('4h').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
            if len(df) < 30:
                continue
            price = float(df['Close'].iloc[-1])

            # ── 주봉 HTF 필터 (CRYPTO 4H 전용, 2026-04-28) ──────
            if USE_HTF_WEEKLY and group_name == 'CRYPTO':
                htf_ok = _check_htf_weekly(df_1h)
                if not htf_ok:
                    print(f"    {name}({code}) 4H | 현재가={price:.2f} | [HTF차단] 주봉 EMA20 하락추세")
                    continue

            sig = _check_signal_with_quality(df, min_q, ticker_code=code, market=group_name)
            if sig:
                fmt = '.2f' if group_name in ('US', 'CRYPTO') else ',.0f'
                print(f"    *** {name}({code}) 4H | {sig['type']} 신호 | "
                      f"현재가={price:{fmt}} | 진입={sig['entry']:{fmt}} | "
                      f"TP=+{sig['tp_pct']:.2f}% | SL={sig['sl_pct']:.2f}%")
                signals.append({'ticker': code, 'name': name,
                                'market': group_name, 'timeframe': '4H',
                                'price': price, **sig})
            else:
                print(f"    {name}({code}) 4H | 현재가={price:.2f} | 신호없음")

    # ── 화이트리스트 검증 (유니버스 외 종목 완전 차단) ──────────────
    # 어떤 경로로 신호가 생성됐든 승인된 유니버스에 없으면 진입 불가
    _KR_WL     = set(KR_SWING_TICKERS.keys())
    _US_WL     = set(US_SWING_TICKERS.keys())
    _CRYPTO_WL = set(CRYPTO_4H_TICKERS.keys()) | set(CRYPTO_TICKERS.keys())
    wl_ok = []
    for s in signals:
        mkt    = s.get('market', 'CRYPTO')
        ticker = s.get('ticker', '')
        if   mkt == 'KR'     and ticker not in _KR_WL:
            print(f"  [유니버스차단] {ticker} KR — 미승인 종목")
            continue
        elif mkt == 'US'     and ticker not in _US_WL:
            print(f"  [유니버스차단] {ticker} US — 미승인 종목 (PLTR 등)")
            continue
        elif mkt == 'CRYPTO' and ticker not in _CRYPTO_WL:
            print(f"  [유니버스차단] {ticker} CRYPTO — 미승인 종목")
            continue
        wl_ok.append(s)
    signals = wl_ok

    # ── 시장별 시간대 필터 ────────────────────────────────────
    current_hour = datetime.now().hour
    filtered = []
    for s in signals:
        mkt = s.get('market', 'CRYPTO')
        allowed = MARKET_HOURS_KST.get(mkt, set(range(0, 24)))
        if current_hour in allowed:
            filtered.append(s)
        else:
            print(f"  [시간대 차단] {s['name']}({s['ticker']}) {mkt} — 현재 {current_hour}시 거래 외 시간")
    signals = filtered

    # ── 종합 랭킹 정렬 ────────────────────────────────────────
    for s in signals:
        s['rank_score'] = _rank_signal(s)
        s['tradeable'] = True

    signals.sort(key=lambda x: x['rank_score'], reverse=True)

    # ── Flexible 한도: Q6~7은 무조건, Q4~5는 상위권만, Q3 이하 차단 ──
    must_take  = [s for s in signals if s.get('quality_score', 0) >= 6]
    can_take   = [s for s in signals if 4 <= s.get('quality_score', 0) < 6]

    # must_take 먼저, 나머지로 MIN_DAILY_SIGNALS까지 채우고 MAX_DAILY_SIGNALS 상한
    tradeable_list = must_take[:]
    remaining_slots = max(MIN_DAILY_SIGNALS - len(tradeable_list), 0)
    tradeable_list += can_take[:remaining_slots]

    # MAX 상한 적용
    tradeable_list = tradeable_list[:MAX_DAILY_SIGNALS]
    tradeable_set  = {id(s) for s in tradeable_list}

    waiting = []
    for s in signals:
        if id(s) not in tradeable_set:
            s['tradeable'] = False
            waiting.append(s)

    print(f"\n  {'='*40}")
    print(f"  총 신호: {len(signals)}건  →  거래 대상: {len(tradeable_list)}건 "
          f"(Q6↑ {len(must_take)}건 우선 + 랭킹순 | 범위: {MIN_DAILY_SIGNALS}~{MAX_DAILY_SIGNALS}건)")
    print(f"\n  [거래 대상]")
    for i, s in enumerate(tradeable_list, 1):
        tf_label = s.get('timeframe', '15m')
        q = s.get('quality_score', 0)
        flag = '★' if q >= 6 else ' '
        print(f"  {i}.{flag} {s['name']}({s['ticker']}) [{tf_label}] | {s['type']} | "
              f"진입={s['entry']} | TP=+{s['tp_pct']:.2f}% | "
              f"Q={q}/7 | 랭크={s['rank_score']:.1f}")

    if waiting:
        print(f"\n  [제외된 신호 — {len(waiting)}건]")
        for s in waiting:
            tf_label = s.get('timeframe', '15m')
            print(f"  - {s['name']}({s['ticker']}) [{tf_label}] | Q={s.get('quality_score',0)}/7 | "
                  f"랭크={s['rank_score']:.1f} → 한도 초과")

    print(f"{'='*65}\n")
    return signals


if __name__ == '__main__':
    scan_all()
