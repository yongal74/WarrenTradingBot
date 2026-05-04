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

# ── Phase 1 시드 자금 (포워드 테스트) ─────────────────────
SEED_KR        = 10_000_000   # 한국주식 시드
SEED_US        = 10_000_000   # 미국주식 시드
SEED_CRYPTO    =  5_000_000   # 코인 시드
TOTAL_SEED     = SEED_KR + SEED_US + SEED_CRYPTO  # 2500만원

# ── 리스크 관리 (트레이드당 2% 리스크) ───────────────────
RISK_PCT_PER_TRADE = 0.02     # 트레이드당 최대 리스크 2%
#   KR  1000만 × 2% = 20만원/trade
#   US  1000만 × 2% = 20만원/trade
#   코인  500만 × 2% = 10만원/trade
MIN_RR             = 2.0      # 최소 손익비 1:2
MAX_POSITION_PCT   = 0.10     # 단일 포지션 최대 10%
DAILY_LOSS_LIMIT   = -0.015  # 일일 손실 한도 -1.5% (V5.0 강화)
WEEKLY_LOSS_LIMIT  = -0.05   # 주간 손실 한도 -5%
MDD_LIMIT          = -0.10   # MDD -10% 봇 자동 정지 (V5.0 강화)
STOP_LOSS_PCT      = -0.015  # 개별 포지션 백스톱 -1.5% (FVG/OB MAX_SL_PCT와 동일)

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

# ── V5.1 추가 리스크 상수 ─────────────────────────────────────────
MAX_SECTOR_POSITIONS = int(os.getenv('MAX_SECTOR_POSITIONS', '2'))   # 동일 섹터 최대 포지션
RISK_PER_TRADE_PCT   = float(os.getenv('RISK_PER_TRADE_PCT', '0.003'))  # Risk-based sizing 기준 (0.3%)
