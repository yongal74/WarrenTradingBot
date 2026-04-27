# -*- coding: utf-8 -*-
"""
Forward Tester — 매일 신호 생성 + Paper Trading 실행
AI Pathways 스타일 Agentic Workflow
"""
import warnings; warnings.filterwarnings('ignore')
import pandas as pd
from datetime import datetime
from pathlib import Path

from config.assets import ALL_ASSETS, PRIMARY_STRATEGY
from config.settings import SIGNAL_LOG_PATH, TRADING_MODE
from data.data_loader import load, get_current_price
from core.strategy_factory import get_signal, get_all_signals, _atr
from core.confluence_engine import (
    compute_score_series, get_latest_scores,
    get_active_confluences, compute_tp_sl, MIN_SCORE
)
from core.portfolio_manager import PortfolioManager
from core.risk_manager import RiskManager
from agents.telegram_agent import TelegramAgent

class ForwardTester:
    def __init__(self):
        self.pm   = PortfolioManager()
        self.rm   = RiskManager(self.pm)
        self.tg   = TelegramAgent()
        self._log = []

    # ── 메인 실행 루프 ─────────────────────────────────────
    def run_daily(self) -> dict:
        """
        1일 1회 호출 — 전체 종목 신호 확인 및 Paper Trade 실행
        Returns: 실행 결과 요약
        """
        ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log = {'timestamp': ts, 'actions': [], 'signals': {}}

        print(f"\n{'='*55}")
        print(f"  WarrenTradingActivebot Daily Run [{ts}]")
        print(f"  모드: {TRADING_MODE}")
        print(f"{'='*55}")

        # Circuit Breaker 체크
        ok, reason = self.rm.check()
        if not ok:
            msg = f"Circuit Breaker: {reason}"
            print(f"\n  {msg}")
            self.tg.notify_circuit_breaker(reason, "당일 거래 중단")
            log['actions'].append({'type':'CIRCUIT_BREAKER', 'msg': reason})
            return log

        prices = {}  # 현재가 캐시

        for ticker, asset in ALL_ASSETS.items():
            market   = asset['market']
            name     = asset['name']
            strategy = PRIMARY_STRATEGY[ticker]

            # 데이터 로드
            df = load(ticker, market)
            if df is None or len(df) < 60:
                print(f"  [{ticker}] 데이터 부족 — 건너뜀")
                continue

            # DatetimeIndex 보장
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            # 현재가
            price = float(df['Close'].iloc[-1])
            prices[ticker] = price

            # 모든 전략 신호 (대시보드용)
            all_sigs = get_all_signals(df)
            log['signals'][ticker] = all_sigs

            # 합류점 스코어 계산
            conf_scores  = get_latest_scores(df)
            active_confs = get_active_confluences(df)
            log.setdefault('confluence', {})[ticker] = {
                'scores':  conf_scores,
                'active':  active_confs,
            }

            # ATR 기반 TP/SL 계산
            atr_val = float(_atr(df).iloc[-1])
            tp_sl   = compute_tp_sl(price, atr_val) if atr_val > 0 else None

            # 1순위 전략 신호
            signal = get_signal(df, strategy)

            # 합류점 신호 (active_confs 있으면 우선)
            use_confluence = len(active_confs) > 0
            effective_signal = 1 if (signal == 1 or use_confluence) else 0

            conf_str = f" | 합류점={active_confs}" if active_confs else ""
            print(f"\n  [{ticker}] {name}")
            print(f"    전략={strategy} | 신호={'📈 매수' if signal==1 else '⏸ 관망'}"
                  f"{conf_str} | 현재가={price:,.2f}")
            if tp_sl:
                print(f"    TP={tp_sl['actual_tp']:,.2f}(+{tp_sl['tp_pct']:.2f}%) | "
                      f"SL={tp_sl['actual_sl']:,.2f}({tp_sl['sl_pct']:.2f}%)")

            action = self._execute(ticker, name, price, effective_signal, strategy,
                                   active_confs=active_confs, tp_sl=tp_sl)
            if action:
                log['actions'].append(action)
                self._log_signal(ticker, strategy, effective_signal, price, action)

        # 손절 체크
        self._check_stop_loss(prices, log)

        # 포트폴리오 요약
        summary = self.pm.summary(prices)
        log['portfolio'] = summary
        self._print_summary(summary)

        return log

    def _execute(self, ticker, name, price, signal, strategy,
                 active_confs=None, tp_sl=None) -> dict | None:
        """신호에 따라 매수/매도 실행"""
        has_pos = self.pm.has_position(ticker)

        if signal == 1 and not has_pos:
            # 매수
            qty = self.rm.position_size(price)
            if qty <= 0:
                return None
            strat_label = f"{strategy}"
            if active_confs:
                strat_label += f"+CONF({','.join(active_confs)})"
            trade = self.pm.buy(ticker, price, qty, strat_label, name)
            if trade:
                amt = price * qty
                tp_info = f" | TP={tp_sl['actual_tp']:,.2f} SL={tp_sl['actual_sl']:,.2f}" if tp_sl else ""
                print(f"    ✅ 매수 실행: {qty}주 @ {price:,.2f} (총 {amt:,.0f}원){tp_info}")
                self.tg.notify_buy(ticker, name, strat_label, price, qty, amt)
                return {'type':'BUY', 'ticker':ticker, 'price':price, 'qty':qty,
                        'tp_sl': tp_sl, 'confluences': active_confs or []}

        elif signal == 0 and has_pos:
            # 청산
            trade = self.pm.sell(ticker, price, reason='전략신호청산')
            if trade:
                print(f"    🔴 매도 실행: {trade['qty']}주 @ {price:,.2f} | PnL={trade['pnl_pct']:+.2f}%")
                self.rm.record_pnl(trade['pnl_pct'] / 100)
                self.tg.notify_sell(ticker, name, strategy, price, trade['qty'],
                                    trade.get('pnl', 0), trade['pnl_pct'], '신호청산')
                return {'type':'SELL', 'ticker':ticker, 'price':price,
                        'pnl_pct': trade['pnl_pct']}

        return None

    def _check_stop_loss(self, prices: dict, log: dict):
        """개별 포지션 손절 체크"""
        for ticker, pos in list(self.pm.positions().items()):
            price = prices.get(ticker)
            if price is None:
                continue
            if self.rm.should_stop_loss(pos['entry_price'], price):
                trade = self.pm.sell(ticker, price, reason='손절')
                if trade:
                    print(f"\n  ⚠️  손절: [{ticker}] {trade['qty']}주 @ {price:,.2f} "
                          f"| PnL={trade['pnl_pct']:+.2f}%")
                    self.rm.record_pnl(trade['pnl_pct'] / 100)
                    self.tg.notify_stop_loss(ticker, pos['entry_price'], price, trade['pnl_pct'])
                    log['actions'].append({'type':'STOP_LOSS', 'ticker':ticker,
                                           'pnl_pct': trade['pnl_pct']})

    def _log_signal(self, ticker, strategy, signal, price, action):
        row = {
            'date':     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ticker':   ticker, 'strategy': strategy,
            'signal':   signal, 'price':    price,
            'action':   action.get('type','')
        }
        df_new = pd.DataFrame([row])
        if SIGNAL_LOG_PATH.exists():
            df_new.to_csv(SIGNAL_LOG_PATH, mode='a', header=False, index=False)
        else:
            df_new.to_csv(SIGNAL_LOG_PATH, index=False)

    def _print_summary(self, s: dict):
        print(f"\n  {'─'*50}")
        print(f"  📊 포트폴리오 요약")
        print(f"  총 자산:    {s['total_value']:>12,.0f}원")
        print(f"  현금:       {s['cash']:>12,.0f}원")
        print(f"  수익률:     {s['return_pct']:>+11.2f}%")
        print(f"  MDD:        {s['mdd_pct']:>+11.2f}%")
        print(f"  오픈 포지션: {s['open_positions']}개")
        print(f"  총 거래:     {s['total_trades']}회 (승률 {s['win_rate']}%)")
        print(f"  {'─'*50}")

    def get_status(self) -> dict:
        """대시보드용 현재 상태 반환"""
        prices = {}
        signals_map = {}
        confluence_map = {}

        for ticker, asset in ALL_ASSETS.items():
            df = load(ticker, asset['market'])
            if df is not None and len(df) >= 60:
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                prices[ticker]       = float(df['Close'].iloc[-1])
                signals_map[ticker]  = get_all_signals(df)
                conf_scores          = get_latest_scores(df)
                active_confs         = get_active_confluences(df)
                atr_val              = float(_atr(df).iloc[-1])
                tp_sl = compute_tp_sl(prices[ticker], atr_val) if atr_val > 0 else None
                confluence_map[ticker] = {
                    'scores':  conf_scores,
                    'active':  active_confs,
                    'tp_sl':   tp_sl,
                }

        return {
            'portfolio':   self.pm.summary(prices),
            'positions':   self.pm.positions(),
            'prices':      prices,
            'signals':     signals_map,
            'confluence':  confluence_map,
            'trade_log':   self.pm.get_trade_log(),
            'circuit_ok':  not self.rm.circuit_open,
        }
