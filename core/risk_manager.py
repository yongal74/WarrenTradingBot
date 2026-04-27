# -*- coding: utf-8 -*-
"""리스크 관리 — Circuit Breaker + 포지션 사이징"""
import pandas as pd
from datetime import datetime, date
from config.settings import (MAX_POSITION_PCT, DAILY_LOSS_LIMIT,
                              WEEKLY_LOSS_LIMIT, MDD_LIMIT, STOP_LOSS_PCT)

class RiskManager:
    def __init__(self, portfolio_manager):
        self.pm = portfolio_manager
        self._daily_loss  = 0.0
        self._weekly_loss = 0.0
        self._last_check_date = date.today()
        self._circuit_open = False  # True면 거래 중단

    # ── Circuit Breaker ──────────────────────────────────────
    def check(self) -> tuple[bool, str]:
        """
        Returns: (OK, reason)
        OK=True면 거래 가능, False면 중단
        """
        self._refresh_daily()

        total = self.pm.total_value()
        initial = self.pm.initial_capital

        # MDD 체크
        peak = self.pm.peak_value()
        mdd  = (total - peak) / peak if peak > 0 else 0
        if mdd <= MDD_LIMIT:
            self._circuit_open = True
            return False, f"MDD 한도 초과({mdd*100:.1f}%) — 봇 자동 정지"

        # 일일 손실
        if self._daily_loss <= DAILY_LOSS_LIMIT:
            return False, f"일일 손실 한도 초과({self._daily_loss*100:.1f}%) — 당일 거래 중단"

        # 주간 손실
        if self._weekly_loss <= WEEKLY_LOSS_LIMIT:
            return False, f"주간 손실 한도 초과({self._weekly_loss*100:.1f}%) — 주간 거래 중단"

        return True, "OK"

    def _refresh_daily(self):
        today = date.today()
        if today != self._last_check_date:
            self._daily_loss = 0.0
            self._last_check_date = today
            # 월요일이면 주간 손실도 초기화
            if today.weekday() == 0:
                self._weekly_loss = 0.0

    def record_pnl(self, pnl_pct: float):
        """거래 결과 기록"""
        self._daily_loss  += pnl_pct
        self._weekly_loss += pnl_pct

    # ── 포지션 사이징 ─────────────────────────────────────────
    def position_size(self, price: float) -> int:
        """
        포트폴리오 MAX_POSITION_PCT 만큼 매수 가능한 수량
        Returns: 주식 수 (int)
        """
        capital   = self.pm.available_cash()
        max_alloc = self.pm.total_value() * MAX_POSITION_PCT
        invest    = min(capital, max_alloc)
        if price <= 0:
            return 0
        return max(1, int(invest / price))

    # ── 손절 체크 ────────────────────────────────────────────
    def should_stop_loss(self, entry_price: float, current_price: float) -> bool:
        if entry_price <= 0:
            return False
        ret = (current_price - entry_price) / entry_price
        return ret <= STOP_LOSS_PCT

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open
