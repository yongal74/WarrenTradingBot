# -*- coding: utf-8 -*-
"""
Warren Trading System v2.0 — 확정 15종목 유니버스
KR 5종목 + US 5종목 + CRYPTO 5종목
핵심 전략: FVG(S17) + OrderBlock(S26)
"""

# 한국주식 (yfinance .KS / FinanceDataReader)
KR_ASSETS = {
    '005930': {'name': '삼성전자',       'yf': '005930.KS', 'strategies': ['S17_FVG', 'S26_OB', 'S01_EMA9_21']},
    '000660': {'name': 'SK하이닉스',     'yf': '000660.KS', 'strategies': ['S17_FVG', 'S26_OB', 'S01_EMA9_21']},
    '009150': {'name': '삼성전기',       'yf': '009150.KS', 'strategies': ['S26_OB',  'S17_FVG', 'S07_RSI_Trend']},
    '034020': {'name': '두산에너빌리티', 'yf': '034020.KS', 'strategies': ['S17_FVG', 'S26_OB', 'S07_RSI_Trend']},
    '008060': {'name': '대덕전자',       'yf': '008060.KS', 'strategies': ['S17_FVG', 'S26_OB', 'S01_EMA9_21']},
}

# 미국주식 (yfinance)
US_ASSETS = {
    'NVDA': {'name': '엔비디아',   'strategies': ['S17_FVG', 'S02_EMA20_50', 'S01_EMA9_21']},
    'PLTR': {'name': '팔란티어',   'strategies': ['S17_FVG', 'S26_OB',       'S07_RSI_Trend']},
    'AMD':  {'name': 'AMD',        'strategies': ['S17_FVG', 'S01_EMA9_21',  'S07_RSI_Trend']},
    'TSLA': {'name': '테슬라',     'strategies': ['S17_FVG', 'S09_MACD',     'S01_EMA9_21']},
    'SOXX': {'name': '반도체ETF',  'strategies': ['S17_FVG', 'S26_OB',       'S02_EMA20_50']},
}

# 코인 (yfinance — BTC/ETH/SOL/XRP 4종 포워드테스트)
CRYPTO_ASSETS = {
    'BTC':  {'name': '비트코인', 'yf': 'BTC-USD', 'strategies': ['S17_FVG', 'S26_OB', 'S07_RSI_Trend']},
    'ETH':  {'name': '이더리움', 'yf': 'ETH-USD', 'strategies': ['S17_FVG', 'S26_OB', 'S01_EMA9_21']},
    'SOL':  {'name': '솔라나',   'yf': 'SOL-USD', 'strategies': ['S17_FVG', 'S26_OB', 'S07_RSI_Trend']},
    'XRP':  {'name': '리플',     'yf': 'XRP-USD', 'strategies': ['S17_FVG', 'S26_OB', 'S09_MACD']},
}

# 전체 통합
ALL_ASSETS = {}
for t, v in KR_ASSETS.items():
    ALL_ASSETS[t] = {**v, 'market': 'KR'}
for t, v in US_ASSETS.items():
    ALL_ASSETS[t] = {**v, 'market': 'US'}
for t, v in CRYPTO_ASSETS.items():
    ALL_ASSETS[t] = {**v, 'market': 'CRYPTO'}

# 종목별 1순위 전략
PRIMARY_STRATEGY = {t: v['strategies'][0] for t, v in ALL_ASSETS.items()}
