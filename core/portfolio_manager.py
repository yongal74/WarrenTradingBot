# -*- coding: utf-8 -*-
"""포트폴리오 관리 — Paper Trading 포지션 추적"""
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from config.settings import PAPER_CAPITAL, TRADE_LOG_PATH, SIGNAL_LOG_PATH

class PortfolioManager:
    def __init__(self):
        self.initial_capital = PAPER_CAPITAL
        self._cash   = PAPER_CAPITAL
        self._positions: dict = {}   # ticker -> {qty, entry_price, strategy, entry_date}
        self._trades:  list   = []   # 체결 내역
        self._peak    = PAPER_CAPITAL
        self._load_state()

    # ── 상태 영속성 ──────────────────────────────────────────
    STATE_FILE = Path(__file__).parent.parent / 'logs' / 'portfolio_state.json'

    def _save_state(self):
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {'cash': self._cash, 'positions': self._positions,
                 'peak': self._peak, 'initial': self.initial_capital}
        with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self):
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self._cash     = state.get('cash',     PAPER_CAPITAL)
                self._positions= state.get('positions',{})
                self._peak     = state.get('peak',     PAPER_CAPITAL)
                self.initial_capital = state.get('initial', PAPER_CAPITAL)
            except Exception:
                pass

    # ── 포지션 진입/청산 ─────────────────────────────────────
    def buy(self, ticker: str, price: float, qty: int, strategy: str, name: str = ''):
        if self._cash < price * qty:
            qty = int(self._cash / price)
        if qty <= 0:
            return None

        cost = price * qty
        self._cash -= cost
        self._positions[ticker] = {
            'qty': qty, 'entry_price': price, 'strategy': strategy,
            'name': name, 'entry_date': datetime.now().isoformat(),
            'market_value': cost
        }
        trade = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ticker': ticker, 'name': name, 'action': 'BUY',
            'qty': qty, 'price': price, 'amount': cost,
            'strategy': strategy, 'pnl': 0.0, 'pnl_pct': 0.0
        }
        self._log_trade(trade)
        self._save_state()
        return trade

    def sell(self, ticker: str, price: float, reason: str = '전략신호'):
        pos = self._positions.get(ticker)
        if not pos:
            return None

        qty        = pos['qty']
        entry      = pos['entry_price']
        proceeds   = price * qty
        pnl        = proceeds - entry * qty
        pnl_pct    = (price - entry) / entry

        self._cash += proceeds
        del self._positions[ticker]

        # 피크 갱신
        tv = self.total_value()
        if tv > self._peak:
            self._peak = tv

        trade = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ticker': ticker, 'name': pos.get('name',''), 'action': 'SELL',
            'qty': qty, 'price': price, 'amount': proceeds,
            'strategy': pos['strategy'], 'pnl': round(pnl,2),
            'pnl_pct': round(pnl_pct*100,2), 'reason': reason
        }
        self._log_trade(trade)
        self._save_state()
        return trade

    def _log_trade(self, trade: dict):
        self._trades.append(trade)
        df_new = pd.DataFrame([trade])
        if TRADE_LOG_PATH.exists():
            df_new.to_csv(TRADE_LOG_PATH, mode='a', header=False, index=False)
        else:
            df_new.to_csv(TRADE_LOG_PATH, index=False)

    # ── 조회 ─────────────────────────────────────────────────
    def available_cash(self) -> float:
        return self._cash

    def total_value(self, prices: dict = None) -> float:
        mv = sum(
            (prices or {}).get(t, p['entry_price']) * p['qty']
            for t, p in self._positions.items()
        )
        return self._cash + mv

    def peak_value(self) -> float:
        return self._peak

    def positions(self) -> dict:
        return self._positions.copy()

    def has_position(self, ticker: str) -> bool:
        return ticker in self._positions

    def get_trade_log(self) -> pd.DataFrame:
        if TRADE_LOG_PATH.exists():
            return pd.read_csv(TRADE_LOG_PATH)
        return pd.DataFrame()

    def summary(self, prices: dict = None) -> dict:
        tv  = self.total_value(prices)
        ret = (tv - self.initial_capital) / self.initial_capital * 100
        mdd = (tv - self._peak) / self._peak * 100 if self._peak > 0 else 0
        trades = self.get_trade_log()
        win_trades = trades[trades['pnl']>0] if len(trades)>0 else pd.DataFrame()
        return {
            'total_value':   round(tv, 0),
            'cash':          round(self._cash, 0),
            'return_pct':    round(ret, 2),
            'mdd_pct':       round(mdd, 2),
            'open_positions':len(self._positions),
            'total_trades':  len(trades),
            'win_trades':    len(win_trades),
            'win_rate':      round(len(win_trades)/len(trades)*100,1) if len(trades)>0 else 0,
        }
