# -*- coding: utf-8 -*-
"""
Warren Trading System v4.6 — 확정 종목 유니버스
KR 16종목 + US 10종목 + CRYPTO 4종목
전략: 종목별 확정 전략 레지스트리 (fvg_ob_tester.py와 동기화)
최종 업데이트: 2026-04-30 V4.6
"""

# ── KR 유니버스 (16종목) ────────────────────────────────────────────
# fvg_ob_tester.py KR_SWING_TICKERS와 동기화
KR_ASSETS = {
    # V4.0 기존 8종목
    '017670': {'name': 'SK텔레콤',          'yf': '017670.KS', 'strategy': 'BB_SWING',    'wr': 85.7},
    '035720': {'name': '카카오',            'yf': '035720.KS', 'strategy': 'BB_SWING',    'wr': 81.8},
    '021240': {'name': '코웨이',            'yf': '021240.KS', 'strategy': 'BB_SWING',    'wr': 78.6},
    '005380': {'name': '현대차',            'yf': '005380.KS', 'strategy': 'BB_SWING',    'wr': 77.8},
    '010140': {'name': '삼성중공업',        'yf': '010140.KS', 'strategy': 'SUPERTREND',  'wr': 75.0},
    '086790': {'name': '하나금융',          'yf': '086790.KS', 'strategy': 'MACD',        'wr': 73.3},
    '034020': {'name': '두산에너빌리티',    'yf': '034020.KS', 'strategy': 'BB_SWING',    'wr': 66.7},
    '272210': {'name': '한화시스템',        'yf': '272210.KS', 'strategy': 'GAPGO',       'wr': 60.0},
    # V4.1 신규 편입 5종목
    '000660': {'name': 'SK하이닉스',        'yf': '000660.KS', 'strategy': 'BB_SWING',    'wr': 55.1},
    '058470': {'name': '리노공업',          'yf': '058470.KS', 'strategy': 'BB_SWING',    'wr': 51.7},
    '064350': {'name': '현대로템',          'yf': '064350.KS', 'strategy': 'BB_SWING',    'wr': 48.4},
    '128940': {'name': '한미약품',          'yf': '128940.KS', 'strategy': 'BB_SWING',    'wr': 44.2},
    '012450': {'name': '한화에어로스페이스','yf': '012450.KS', 'strategy': 'BB_SWING',    'wr': 43.7},
    # V4.5 추가 3종목
    '005930': {'name': '삼성전자',          'yf': '005930.KS', 'strategy': 'MOMENTUM',    'wr': 56.5},
    '009150': {'name': '삼성전기',          'yf': '009150.KS', 'strategy': 'BB_SWING',    'wr': 52.9},
    '008060': {'name': '대덕전자',          'yf': '008060.KS', 'strategy': 'BB_SWING',    'wr': 56.5},
}

# ── US 유니버스 (10종목) ────────────────────────────────────────────
# fvg_ob_tester.py US_SWING_TICKERS와 동기화
# 퇴출: PLTR(유니버스 외), SOXX(ETF, 전략 불일치)
US_ASSETS = {
    # V4.0 기존 5종목
    'AMD':  {'name': 'AMD',               'yf': 'AMD',   'strategy': 'BB_REVERSAL', 'wr': 87.5},
    'MU':   {'name': '마이크론',          'yf': 'MU',    'strategy': 'SUPERTREND',  'wr': 80.0},
    'NVDA': {'name': '엔비디아',          'yf': 'NVDA',  'strategy': 'MACD',        'wr': 72.7},
    'AVGO': {'name': '브로드컴',          'yf': 'AVGO',  'strategy': 'SUPERTREND',  'wr': 66.7},
    'MSTR': {'name': '마이크로스트래티지','yf': 'MSTR',  'strategy': 'BB_MOM',      'wr': 60.0},
    # V4.1 신규 편입 5종목
    'LRCX': {'name': '램리서치',          'yf': 'LRCX',  'strategy': 'BB_MOM',      'wr': 42.4},
    'AMZN': {'name': '아마존',            'yf': 'AMZN',  'strategy': 'BB_MOM',      'wr': 41.0},
    'SHOP': {'name': '쇼피파이',          'yf': 'SHOP',  'strategy': 'BB_MOM',      'wr': 38.7},
    'GOOGL':{'name': '구글',              'yf': 'GOOGL', 'strategy': 'BB_MOM',      'wr': 38.5},
    'TSLA': {'name': '테슬라',            'yf': 'TSLA',  'strategy': 'MACD',        'wr': 37.5},
}

# ── CRYPTO 유니버스 (4종목) ─────────────────────────────────────────
# 15m 전략: FVG+OB / 4H 전략: FVG+OB R:R 1:3
CRYPTO_ASSETS = {
    'BTC':  {'name': '비트코인', 'yf': 'BTC-USD',  'strategy': 'FVG+OB', 'tf_4h': True,  'tf_15m': True},
    'ETH':  {'name': '이더리움', 'yf': 'ETH-USD',  'strategy': 'FVG+OB', 'tf_4h': False, 'tf_15m': True},
    'SOL':  {'name': '솔라나',   'yf': 'SOL-USD',  'strategy': 'FVG+OB', 'tf_4h': True,  'tf_15m': True},
    'XRP':  {'name': '리플',     'yf': 'XRP-USD',  'strategy': 'FVG+OB', 'tf_4h': True,  'tf_15m': True},
}

# ── 전체 통합 ────────────────────────────────────────────────────────
ALL_ASSETS: dict = {}
for _t, _v in KR_ASSETS.items():
    ALL_ASSETS[_t] = {**_v, 'market': 'KR'}
for _t, _v in US_ASSETS.items():
    ALL_ASSETS[_t] = {**_v, 'market': 'US'}
for _t, _v in CRYPTO_ASSETS.items():
    ALL_ASSETS[_t] = {**_v, 'market': 'CRYPTO'}

# ── 편의 세트 ───────────────────────────────────────────────────────
KR_TICKERS_SET    = set(KR_ASSETS.keys())
US_TICKERS_SET    = set(US_ASSETS.keys())
CRYPTO_TICKERS_SET = set(CRYPTO_ASSETS.keys())
ALL_TICKERS_SET   = KR_TICKERS_SET | US_TICKERS_SET | CRYPTO_TICKERS_SET

# ── 종목별 1순위 전략 ───────────────────────────────────────────────
PRIMARY_STRATEGY = {t: v['strategy'] for t, v in ALL_ASSETS.items()}
