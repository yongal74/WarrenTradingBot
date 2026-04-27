# -*- coding: utf-8 -*-
"""Telegram 알림 에이전트 — 매매신호, 포트폴리오 리포트, 서킷브레이커 알림"""
import sys, os, json, requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

class TelegramAgent:
    """Telegram Bot API를 통한 알림 발송"""

    def __init__(self):
        self.token   = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)
        self._base   = f"https://api.telegram.org/bot{self.token}"

    # ── 저수준 발송 ────────────────────────────────────────────
    def _send(self, text: str, parse_mode='HTML') -> bool:
        if not self.enabled:
            print(f"[TelegramAgent] (disabled) {text[:80]}")
            return False
        try:
            r = requests.post(
                f"{self._base}/sendMessage",
                json={'chat_id': self.chat_id, 'text': text, 'parse_mode': parse_mode},
                timeout=10
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[TelegramAgent] 발송 실패: {e}")
            return False

    # ── 매매 신호 알림 ─────────────────────────────────────────
    def notify_buy(self, ticker: str, name: str, strategy: str,
                   price: float, qty: int, amount: float):
        msg = (
            f"<b>📈 매수 체결</b>\n"
            f"종목: <b>{ticker}</b> ({name})\n"
            f"전략: <code>{strategy}</code>\n"
            f"가격: {price:,.2f}  |  수량: {qty:,}\n"
            f"금액: {amount:,.0f}원\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return self._send(msg)

    def notify_sell(self, ticker: str, name: str, strategy: str,
                    price: float, qty: int, pnl: float, pnl_pct: float, reason: str = '신호'):
        icon  = '📉' if pnl < 0 else '💰'
        color = '🔴' if pnl < 0 else '🟢'
        msg = (
            f"<b>{icon} 매도 체결 ({reason})</b>\n"
            f"종목: <b>{ticker}</b> ({name})\n"
            f"전략: <code>{strategy}</code>\n"
            f"가격: {price:,.2f}  |  수량: {qty:,}\n"
            f"{color} PnL: {pnl:+,.0f}원 ({pnl_pct:+.2f}%)\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return self._send(msg)

    def notify_stop_loss(self, ticker: str, entry: float, current: float, pnl_pct: float):
        msg = (
            f"<b>🚨 손절 실행</b>\n"
            f"종목: <b>{ticker}</b>\n"
            f"진입가: {entry:,.2f}  →  현재가: {current:,.2f}\n"
            f"손실: <b>{pnl_pct:+.2f}%</b>\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return self._send(msg)

    # ── 서킷브레이커 알림 ──────────────────────────────────────
    def notify_circuit_breaker(self, reason: str, detail: str):
        msg = (
            f"<b>⛔ 서킷브레이커 발동!</b>\n"
            f"사유: {reason}\n"
            f"내용: {detail}\n"
            f"→ 당일/주간 거래 자동 중단\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return self._send(msg)

    def notify_mdd_stop(self, mdd_pct: float):
        msg = (
            f"<b>🛑 봇 자동 정지 — MDD 한도 초과</b>\n"
            f"현재 MDD: <b>{mdd_pct:.2f}%</b> (한도: -15%)\n"
            f"→ 즉시 수동 확인 필요\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return self._send(msg)

    # ── 일일 리포트 ────────────────────────────────────────────
    def send_daily_report(self, status: dict):
        port   = status.get('portfolio', {})
        tv     = port.get('total_value', 0)
        ret    = port.get('return_pct', 0)
        mdd    = port.get('mdd_pct', 0)
        cash   = port.get('cash', 0)
        pos_n  = port.get('open_positions', 0)
        trades = port.get('total_trades', 0)
        wr     = port.get('win_rate', 0)

        # 포지션 목록
        pos_lines = []
        for tkr, p in status.get('positions', {}).items():
            cur = status.get('prices', {}).get(tkr, p['entry_price'])
            pnl_pct = (cur - p['entry_price']) / p['entry_price'] * 100
            icon = '🟢' if pnl_pct >= 0 else '🔴'
            pos_lines.append(f"  {icon} {tkr}: {pnl_pct:+.2f}% [{p['strategy']}]")

        pos_block = '\n'.join(pos_lines) if pos_lines else '  (포지션 없음)'

        color_ret = '🟢' if ret >= 0 else '🔴'
        msg = (
            f"<b>📊 WarrenBot 일일 리포트</b>\n"
            f"{datetime.now().strftime('%Y-%m-%d')} 기준\n"
            f"{'─'*28}\n"
            f"총 자산:  {tv:>14,.0f}원\n"
            f"현금:     {cash:>14,.0f}원\n"
            f"{color_ret} 수익률: <b>{ret:+.2f}%</b>\n"
            f"MDD:      <b>{mdd:+.2f}%</b>\n"
            f"포지션:   {pos_n}개 | 거래: {trades}회 | 승률: {wr:.1f}%\n"
            f"{'─'*28}\n"
            f"<b>포지션 현황:</b>\n{pos_block}\n"
            f"{'─'*28}\n"
            f"모드: PAPER TRADING"
        )
        return self._send(msg)

    # ── 시스템 시작/종료 알림 ─────────────────────────────────
    def notify_bot_start(self):
        msg = (
            f"<b>🚀 WarrenTradingActivebot 시작</b>\n"
            f"모드: PAPER TRADING\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return self._send(msg)

    def notify_bot_stop(self, reason: str = '정상 종료'):
        msg = (
            f"<b>⏹ WarrenTradingActivebot 종료</b>\n"
            f"사유: {reason}\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return self._send(msg)

    def test_connection(self) -> bool:
        if not self.enabled:
            print("[TelegramAgent] 토큰/채팅ID 미설정. .env 파일에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 추가 필요.")
            return False
        return self._send("WarrenTradingActivebot 연결 테스트 성공!")


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
    agent = TelegramAgent()
    agent.test_connection()
