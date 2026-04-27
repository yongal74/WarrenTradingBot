# -*- coding: utf-8 -*-
"""
WarrenTradingActivebot — 메인 실행기
사용법:
  python main.py           # 1회 실행 (Forward Testing 1일치)
  python main.py --loop    # 매일 장 마감 후 자동 반복
  python main.py --status  # 현재 포트폴리오 상태 출력
"""
import sys, io, warnings, argparse, time
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, time as dtime
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')
from core.forward_tester import ForwardTester
from agents.report_agent import ReportAgent

def run_once():
    print(f"\n{'='*55}")
    print(f"  WarrenTradingActivebot Forward Tester")
    print(f"  실행: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")
    ft = ForwardTester()
    ft.tg.notify_bot_start()
    result = ft.run_daily()
    print(f"\n✅ 완료. actions={len(result.get('actions',[]))}")
    # 일일 리포트 발송
    ReportAgent().run()
    return result

def run_loop():
    """매일 미국 장 마감 후(한국시간 06:00) 자동 실행"""
    print("WarrenTradingActivebot 루프 모드 시작 (Ctrl+C로 종료)")
    ft = ForwardTester()
    while True:
        now = datetime.now()
        # 평일에만 실행
        if now.weekday() < 5:
            # 한국시간 06:00~07:00 사이에 실행 (미국 장 마감 후)
            if dtime(6, 0) <= now.time() <= dtime(7, 0):
                print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}] 일일 실행 시작...")
                ft.run_daily()
                ReportAgent().run()
                # 실행 후 2시간 대기 (중복 실행 방지)
                time.sleep(7200)
                continue
        # 60초마다 체크
        time.sleep(60)

def show_status():
    ft = ForwardTester()
    status = ft.get_status()
    port = status['portfolio']
    print(f"\n{'='*50}")
    print(f"  포트폴리오 현황")
    print(f"{'='*50}")
    print(f"  총 자산:    {port['total_value']:>12,.0f}원")
    print(f"  현금:       {port['cash']:>12,.0f}원")
    print(f"  수익률:     {port['return_pct']:>+11.2f}%")
    print(f"  MDD:        {port['mdd_pct']:>+11.2f}%")
    print(f"  포지션:      {port['open_positions']}개")
    print(f"  총 거래:     {port['total_trades']}회 (승률 {port['win_rate']}%)")
    print(f"\n  오픈 포지션:")
    for t, p in status['positions'].items():
        price = status['prices'].get(t, p['entry_price'])
        pnl   = (price - p['entry_price']) / p['entry_price'] * 100
        print(f"    [{t}] {p['strategy']} | 진입={p['entry_price']:.2f} 현재={price:.2f} PnL={pnl:+.2f}%")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='WarrenTradingActivebot')
    parser.add_argument('--loop',   action='store_true', help='매일 자동 반복')
    parser.add_argument('--status', action='store_true', help='현재 상태 출력')
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.loop:
        run_loop()
    else:
        run_once()
