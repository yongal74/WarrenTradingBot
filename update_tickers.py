# -*- coding: utf-8 -*-
"""V4.0 종목 유니버스 업데이트 스크립트"""
import re

path = 'C:/WarrenTradingActivebot-1.0.0/WarrenTradingActivebot-1.0.0/core/fvg_ob_tester.py'
content = open(path, encoding='utf-8').read()

# ── 1. KR_SWING_TICKERS 교체 ──────────────────────────────────
new_kr = """KR_SWING_TICKERS = {
    # V4.0 BB반등 전략 검증 상위 8종목 (2026-04-29)
    # 다전략 백테스트: 98종목 x 6전략 -> BB반등(S5) 1위 확정
    '017670': ('SK텔레콤',   '017670.KS'),   # BB반등 WR85.7% EV+5.23% PF=9.94
    '035720': ('카카오',     '035720.KS'),   # BB반등 WR81.8% EV+2.44% PF=4.58
    '021240': ('코웨이',     '021240.KS'),   # BB반등 WR78.6% EV+2.67% PF=5.24
    '005380': ('현대차',     '005380.KS'),   # BB반등 WR77.8% EV+3.82% PF=6.00
    '010140': ('삼성중공업', '010140.KS'),   # SuperTrend WR75.0% EV+5.15%
    '086790': ('하나금융',   '086790.KS'),   # MACD WR73.3% EV+1.87%
    '034020': ('두산에너빌', '034020.KS'),   # BB반등 WR66.7% EV+4.22%
    '272210': ('한화시스템', '272210.KS'),   # GapGo WR60.0% EV+7.96%
}"""

# KR_SWING_TICKERS 블록 전체를 정규식으로 교체
content = re.sub(
    r'KR_SWING_TICKERS\s*=\s*\{[^}]*(?:\{[^}]*\}[^}]*)?\}',
    new_kr,
    content,
    flags=re.DOTALL
)
print("1. KR_SWING_TICKERS 교체 완료")

# ── 2. US_SWING_TICKERS 교체 ──────────────────────────────────
new_us = """US_SWING_TICKERS = {
    # V4.0 BB반등+Momentum 검증 5종목 (2026-04-29)
    'AMD':  ('AMD',           'AMD'),    # BB반등 WR87.5% EV+1.89% PF=6.49
    'MU':   ('마이크론',      'MU'),     # SuperTrend WR80.0% EV+1.96%
    'NVDA': ('엔비디아',      'NVDA'),   # MACD WR72.7% EV+1.27%
    'AVGO': ('브로드컴',      'AVGO'),   # SuperTrend WR66.7% EV+2.75%
    'MSTR': ('마이크로스트레티지', 'MSTR'), # BB반등 WR60.0% EV+3.10%
}"""

content = re.sub(
    r'US_SWING_TICKERS\s*=\s*\{[^}]*(?:\{[^}]*\}[^}]*)?\}',
    new_us,
    content,
    flags=re.DOTALL
)
print("2. US_SWING_TICKERS 교체 완료")

# ── 3. CRYPTO_4H_TICKERS 교체 (BTC/SOL/XRP/DOGE 4종만) ───────
new_crypto4h = """CRYPTO_4H_TICKERS = {
    # V4.0 FVG+OB 4H 검증 4종목 (2026-04-29, R:R 1:3)
    # BEP WR=25%, 실제 WR 27~31% -> 수익 구조 성립
    'SOL':  ('솔라나',    'SOL-USD'),   # WR28.5% EV+0.209% 월+1.81%
    'DOGE': ('도지코인',  'DOGE-USD'),  # WR28.8% EV+0.193% 월+1.71%
    'BTC':  ('비트코인',  'BTC-USD'),   # WR31.5% EV+0.187% 월+1.41%
    'XRP':  ('리플',      'XRP-USD'),   # WR26.9% EV+0.137% 월+1.21%
}"""

content = re.sub(
    r'CRYPTO_4H_TICKERS\s*=\s*\{[^}]*(?:\{[^}]*\}[^}]*)?\}',
    new_crypto4h,
    content,
    flags=re.DOTALL
)
print("3. CRYPTO_4H_TICKERS 교체 완료")

open(path, 'w', encoding='utf-8').write(content)
print("\n fvg_ob_tester.py 저장 완료")

# ── 4. run_paper_trading.py YF_TICKER + INITIAL_CAPITAL 업데이트 ──
pt_path = 'C:/WarrenTradingActivebot-1.0.0/WarrenTradingActivebot-1.0.0/run_paper_trading.py'
pt = open(pt_path, encoding='utf-8').read()

# INITIAL_CAPITAL
pt = re.sub(
    r"INITIAL_CAPITAL\s*=\s*\{[^}]*\}",
    """INITIAL_CAPITAL = {
    'KR':     10_000_000,   # 1,000만 (V4.0)
    'US':     10_000_000,   # 1,000만 (V4.0)
    'CRYPTO':  5_000_000,   # 500만   (V4.0)
}""",
    pt, flags=re.DOTALL
)
print("4. INITIAL_CAPITAL 업데이트 완료")

# YF_TICKER
pt = re.sub(
    r"YF_TICKER\s*=\s*\{[^}]*\}",
    """YF_TICKER = {
    # KR V4.0 (8종목)
    '017670': '017670.KS', '035720': '035720.KS',
    '021240': '021240.KS', '005380': '005380.KS',
    '010140': '010140.KS', '086790': '086790.KS',
    '034020': '034020.KS', '272210': '272210.KS',
    # US V4.0 (5종목)
    'AMD': 'AMD', 'MU': 'MU', 'NVDA': 'NVDA', 'AVGO': 'AVGO', 'MSTR': 'MSTR',
    # CRYPTO V4.0 (4종목)
    'SOL': 'SOL-USD', 'DOGE': 'DOGE-USD', 'BTC': 'BTC-USD', 'XRP': 'XRP-USD',
}""",
    pt, flags=re.DOTALL
)
print("5. YF_TICKER 업데이트 완료")

open(pt_path, 'w', encoding='utf-8').write(pt)
print("\n run_paper_trading.py 저장 완료")
print("\n=== V4.0 종목 업데이트 완료 ===")
print("KR 8종목: SK텔레콤, 카카오, 코웨이, 현대차, 삼성중공업, 하나금융, 두산에너빌, 한화시스템")
print("US 5종목: AMD, 마이크론, 엔비디아, 브로드컴, MSTR")
print("CRYPTO 4종목: SOL, DOGE, BTC, XRP")
