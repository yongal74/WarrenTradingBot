# -*- coding: utf-8 -*-
"""리포트 에이전트 — 일일 성과 요약을 파일+Telegram으로 발송"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.telegram_agent import TelegramAgent

class ReportAgent:
    def __init__(self):
        self.tg      = TelegramAgent()
        self.log_dir = Path(__file__).parent.parent / 'logs'

    def run(self):
        try:
            from core.forward_tester import ForwardTester
            ft     = ForwardTester()
            status = ft.get_status()
        except Exception as e:
            print(f"[ReportAgent] 상태 로드 실패: {e}")
            return

        # 일일 리포트 파일 저장
        today = datetime.now().strftime('%Y-%m-%d')
        report_path = self.log_dir / f"daily_report_{today}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2, default=str)
        print(f"[ReportAgent] 리포트 저장: {report_path}")

        # Telegram 발송
        ok = self.tg.send_daily_report(status)
        if ok:
            print("[ReportAgent] Telegram 리포트 발송 완료")
        else:
            print("[ReportAgent] Telegram 비활성화 — 콘솔 출력만")

        # 콘솔 출력
        port = status.get('portfolio', {})
        print(f"\n{'='*45}")
        print(f"  일일 리포트 — {today}")
        print(f"{'='*45}")
        print(f"  총 자산:  {port.get('total_value',0):>14,.0f}원")
        print(f"  수익률:   {port.get('return_pct',0):>+13.2f}%")
        print(f"  MDD:      {port.get('mdd_pct',0):>+13.2f}%")
        print(f"  포지션:   {port.get('open_positions',0)}개")
        print(f"  거래횟수: {port.get('total_trades',0)}회  승률: {port.get('win_rate',0):.1f}%")
        print(f"{'='*45}\n")
        return status


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
    ReportAgent().run()
