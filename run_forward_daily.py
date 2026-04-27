# -*- coding: utf-8 -*-
"""
Warren FVG+OB 일일 포워드 테스터
실행 시 KR5 + US5 전종목 신호 스캔 → CSV 로그 → 텔레그램 알림

스케줄:
  09:00  한국장 시작 스캔
  22:30  미국장 시작 스캔
  06:10  아침 리포트 (전일 로그 요약)

사용법:
  python run_forward_daily.py          # 즉시 스캔
  python run_forward_daily.py --report # 전일 로그 요약 리포트
"""
import sys
import os
import argparse
import csv
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

# Windows 콘솔 UTF-8 강제 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass

from core.fvg_ob_tester import scan_all

# ── 경로 설정 ────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
LOG_DIR      = BASE_DIR / 'logs'
SIGNAL_LOG   = LOG_DIR / 'forward_signals.csv'
REPORT_LOG   = LOG_DIR / 'forward_report.txt'

LOG_DIR.mkdir(parents=True, exist_ok=True)

# CSV 헤더
CSV_FIELDS = [
    'datetime', 'session', 'ticker', 'name', 'market',
    'type', 'price', 'entry', 'sl', 'tp',
    'sl_pct', 'tp_pct', 'zone_high', 'zone_low',
]


def _session_name() -> str:
    h = datetime.now().hour
    if 6 <= h < 16:
        return 'KR'
    elif 22 <= h or h < 6:
        return 'US'
    return 'PRE'


def save_signals(signals: list, session: str):
    """신호를 CSV 로그에 누적 저장"""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    write_header = not SIGNAL_LOG.exists()

    with open(SIGNAL_LOG, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for s in signals:
            row = {
                'datetime':  now_str,
                'session':   session,
                'ticker':    s.get('ticker', ''),
                'name':      s.get('name', ''),
                'market':    s.get('market', ''),
                'type':      s.get('type', ''),
                'price':     s.get('price', 0),
                'entry':     s.get('entry', 0),
                'sl':        s.get('sl', 0),
                'tp':        s.get('tp', 0),
                'sl_pct':    s.get('sl_pct', 0),
                'tp_pct':    s.get('tp_pct', 0),
                'zone_high': s.get('zone_high', 0),
                'zone_low':  s.get('zone_low', 0),
            }
            writer.writerow(row)

    print(f"\n  [로그] {len(signals)}건 저장 → {SIGNAL_LOG}")


def send_telegram(msg: str):
    """텔레그램 발송 (토큰 미설정시 스킵)"""
    token   = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        print("  [Telegram] 미설정 — .env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 추가 필요")
        return
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'},
            timeout=10,
        )
        if r.status_code == 200:
            print("  [Telegram] 전송 완료")
        else:
            print(f"  [Telegram] 전송 실패 {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  [Telegram] 오류: {e}")


def build_signal_message(signals: list, session: str) -> str:
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not signals:
        return (
            f"<b>[Warren FVG+OB] {session} 스캔</b>\n"
            f"{now_str}\n"
            f"신호 없음 — 관망"
        )

    lines = [
        f"<b>[Warren FVG+OB] {session} 신호 {len(signals)}건</b>",
        f"{now_str}",
        "─" * 28,
    ]
    for s in signals:
        mkt = s.get('market', '')
        fmt = ',.0f' if mkt == 'KR' else '.2f'
        lines.append(
            f"<b>{s['name']}({s['ticker']})</b> [{s['type']}]\n"
            f"  현재가={s['price']:{fmt}}  진입={s['entry']:{fmt}}\n"
            f"  TP=+{s['tp_pct']:.2f}%  SL={s['sl_pct']:.2f}%"
        )
    lines.append("─" * 28)
    lines.append("R:R = 1:2 | 구간 만료시 신호 취소")
    return "\n".join(lines)


def run_scan():
    """즉시 스캔 + 로그 + 텔레그램"""
    session = _session_name()
    signals = scan_all()
    if signals:
        save_signals(signals, session)
    msg = build_signal_message(signals, session)
    send_telegram(msg)
    return signals


def run_report():
    """전일 로그 파일 요약 리포트 생성 + 텔레그램 발송"""
    if not SIGNAL_LOG.exists():
        print("  [리포트] 로그 파일 없음")
        send_telegram("<b>[Warren] 아침 리포트</b>\n신호 로그 없음")
        return

    import pandas as pd
    df = pd.read_csv(SIGNAL_LOG, encoding='utf-8-sig')
    if df.empty:
        send_telegram("<b>[Warren] 아침 리포트</b>\n어제 신호 없음")
        return

    # 전일 날짜 필터
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    df['date'] = df['datetime'].str[:10]
    ydf = df[df['date'] == yesterday]

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    total_all  = len(df)
    total_yest = len(ydf)

    lines = [
        f"<b>[Warren] 아침 리포트 {now_str}</b>",
        f"어제({yesterday}) 신호: {total_yest}건",
        f"누적 신호: {total_all}건",
        "─" * 28,
    ]

    if not ydf.empty:
        for _, row in ydf.iterrows():
            mkt = row.get('market', '')
            fmt = ',.0f' if mkt == 'KR' else '.2f'
            lines.append(
                f"{row['ticker']}({row['type']}) "
                f"진입={float(row['entry']):{fmt}} "
                f"TP=+{row['tp_pct']:.2f}% SL={row['sl_pct']:.2f}%"
            )
    else:
        lines.append("어제 신호 없음 — 관망")

    lines.append("─" * 28)
    lines.append("FVG+OB 15분봉 R:R=1:2")

    msg = "\n".join(lines)
    print("\n" + msg.replace("<b>", "").replace("</b>", ""))

    # txt 리포트 저장
    with open(REPORT_LOG, 'a', encoding='utf-8') as f:
        f.write(msg.replace("<b>", "").replace("</b>", "") + "\n\n")

    send_telegram(msg)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true', help='전일 리포트 출력')
    args = parser.parse_args()

    if args.report:
        run_report()
    else:
        run_scan()
