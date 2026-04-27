# -*- coding: utf-8 -*-
"""전역 설정"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')

# 모드
TRADING_MODE   = os.getenv('TRADING_MODE', 'PAPER')   # PAPER / LIVE
PAPER_CAPITAL  = float(os.getenv('PAPER_CAPITAL', '10000000'))

# 리스크 한도 (CLAUDE.md 준수)
MAX_POSITION_PCT   = 0.10   # 단일 포지션 최대 10%
DAILY_LOSS_LIMIT   = -0.02  # 일일 손실 -2%
WEEKLY_LOSS_LIMIT  = -0.05  # 주간 손실 -5%
MDD_LIMIT          = -0.15  # MDD -15% 봇 정지
STOP_LOSS_PCT      = -0.07  # 개별 포지션 손절 -7%

# 데이터 설정
DATA_START         = '2023-01-01'
LOOKBACK_DAYS      = 300     # 지표 계산용 과거 데이터

# 경로
LOG_DIR            = BASE_DIR / 'logs'
REPORT_DIR         = BASE_DIR / 'reports'
DATA_CACHE_DIR     = BASE_DIR / 'data' / 'cache'
for d in [LOG_DIR, REPORT_DIR, DATA_CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TRADE_LOG_PATH     = LOG_DIR / 'trade_log.csv'
SIGNAL_LOG_PATH    = LOG_DIR / 'signals.csv'
SYSTEM_LOG_PATH    = LOG_DIR / 'system.log'

# Alpaca (Live용)
ALPACA_API_KEY     = os.getenv('ALPACA_API_KEY', '')
ALPACA_SECRET_KEY  = os.getenv('ALPACA_SECRET_KEY', '')
ALPACA_BASE_URL    = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# 텔레그램
TELEGRAM_TOKEN     = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')
