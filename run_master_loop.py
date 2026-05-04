# -*- coding: utf-8 -*-
"""
Warren Master Loop — 자동화 핵심 오케스트레이터
================================================
Task Scheduler가 15분마다 이 스크립트를 호출한다.

흐름:
  1. Paper Trading 스캔 + 진입/청산 실행
  2. 결과 로그 기록 (logs/master_loop.log)
  3. 누적 거래 수 >= 10건이면 학습 루프 실행
  4. 학습 결과 → strategy_proposals.json 저장 (자동 적용 절대 금지)
  5. 제안 있으면 텔레그램 알림 → 사용자가 Claude Code와 논의 후 수동 승인

★ 전략 파라미터는 반드시 사람이 승인해야만 바뀐다.
"""
import sys, json, subprocess, os
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR       = Path(__file__).parent
LOG_DIR        = BASE_DIR / 'logs'
TRADES_FILE    = LOG_DIR / 'paper_trades.csv'
MASTER_LOG     = LOG_DIR / 'master_loop.log'
PROPOSALS_FILE = LOG_DIR / 'strategy_proposals.json'
PARAMS_FILE    = LOG_DIR / 'strategy_params.json'
PYTHON         = sys.executable

LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── 로깅 ─────────────────────────────────────────────────────────
def log(msg: str):
    ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # bat 리다이렉트(>> logs\master_loop.log)와 충돌 방지: PermissionError 무시
    try:
        with open(MASTER_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except (PermissionError, OSError):
        pass  # stdout 리다이렉트가 이미 로그를 기록 중


# ── 텔레그램 ─────────────────────────────────────────────────────
def _send_telegram(text: str):
    try:
        token   = os.getenv('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        if not token or not chat_id:
            # .env 직접 로드
            env_path = BASE_DIR / '.env'
            if env_path.exists():
                for line in env_path.read_text(encoding='utf-8').splitlines():
                    if '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip()
            token   = os.getenv('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        if not token or not chat_id:
            return
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        log(f"  텔레그램 전송 실패: {e}")


# ── 거래 건수 확인 ────────────────────────────────────────────────
def _trade_count() -> int:
    if not TRADES_FILE.exists():
        return 0
    try:
        import csv
        with open(TRADES_FILE, encoding='utf-8-sig') as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


# ── 포트폴리오 현황 파싱 ──────────────────────────────────────────
def _parse_summary(output: str) -> dict:
    """run_paper_trading.py 출력에서 핵심 수치 추출"""
    result = {'trades': 0, 'wr': 0.0, 'pnl': 0, 'open': 0, 'entries': 0, 'exits': 0}
    for line in output.splitlines():
        if '누적거래=' in line:
            import re
            m = re.search(r'누적거래=(\d+).*?승률=([\d.]+)%.*?실현손익=([+\-\d,]+)원.*?오픈=(\d+)', line)
            if m:
                result['trades'] = int(m.group(1))
                result['wr']     = float(m.group(2))
                result['pnl']    = int(m.group(3).replace(',', ''))
                result['open']   = int(m.group(4))
        if '신규 진입' in line and '건' in line:
            import re
            m = re.search(r'(\d+)건', line)
            if m:
                result['entries'] = int(m.group(1))
        if 'TP 청산' in line or 'SL 청산' in line:
            result['exits'] += 1
    return result


# ── 제안 저장 (잠금) ─────────────────────────────────────────────
def _save_proposal(proposals: list):
    """학습 제안을 LOCKED 상태로 저장 — 절대 자동 적용 안 함"""
    existing = []
    if PROPOSALS_FILE.exists():
        try:
            existing = json.loads(PROPOSALS_FILE.read_text(encoding='utf-8'))
        except Exception:
            existing = []

    new_entry = {
        'timestamp':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status':     'PENDING',   # PENDING / APPROVED / REJECTED
        'proposals':  proposals,
        'approved_by': None,
        'approved_at': None,
        'note':       '사용자 승인 필요 — Claude Code와 논의 후 수동 적용',
    }
    existing.append(new_entry)
    PROPOSALS_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    log(f"  전략 제안 저장됨 (PENDING) → {PROPOSALS_FILE.name}")


# ── Step 1: Paper Trading 실행 ────────────────────────────────────
def step_paper_trading() -> dict:
    log("=" * 60)
    log("STEP 1: Paper Trading 스캔 실행")
    try:
        result = subprocess.run(
            [PYTHON, str(BASE_DIR / 'run_paper_trading.py')],
            capture_output=True, text=True, timeout=90,
            cwd=str(BASE_DIR), encoding='utf-8', errors='replace'
        )
        output = result.stdout + result.stderr
        for line in output.splitlines():
            if any(k in line for k in ['진입', '청산', '오픈', '누적', '신호', '차단', '오류']):
                log(f"  {line.strip()}")
        summary = _parse_summary(output)
        log(f"  → 누적={summary['trades']}건 | WR={summary['wr']}% | 손익={summary['pnl']:+,}원 | 오픈={summary['open']}개")
        return summary
    except subprocess.TimeoutExpired:
        log("  [오류] Paper trading 타임아웃 (90초)")
        return {}
    except Exception as e:
        log(f"  [오류] {e}")
        return {}


# ── Step 2: 학습 루프 (충분한 데이터 있을 때만) ───────────────────
def step_learning(trade_count: int) -> list:
    """최소 10건 이상일 때 학습. 제안 목록만 반환 — 적용은 절대 안 함."""
    if trade_count < 10:
        log(f"STEP 2: 학습 건너뜀 (거래 {trade_count}건 < 10건 기준)")
        return []

    log(f"STEP 2: 학습 루프 실행 (거래 {trade_count}건)")
    try:
        result = subprocess.run(
            [PYTHON, str(BASE_DIR / 'run_learning_loop.py')],
            capture_output=True, text=True, timeout=60,
            cwd=str(BASE_DIR), encoding='utf-8', errors='replace'
        )
        output = result.stdout + result.stderr
        proposals = []

        # 학습 리포트에서 제안 추출
        report_path = LOG_DIR / 'learning_report.json'
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
                recs = report.get('recommendations', [])
                for r in recs:
                    proposals.append({
                        'type':    r.get('type', 'FILTER'),
                        'item':    r.get('filter' or r.get('item', '')),
                        'reason':  r.get('reason', ''),
                        'effect':  r.get('effect', ''),
                        'status':  'PENDING',
                    })
                log(f"  → 제안 {len(proposals)}건 발굴")
            except Exception:
                pass

        return proposals
    except Exception as e:
        log(f"  [오류] 학습 루프 실패: {e}")
        return []


# ── Step 2b: V6.0 레짐 감지 + 전략 로테이션 제안 ──────────────────
def step_regime_rotation() -> dict | None:
    """마켓 레짐 감지 후 전략 로테이션 제안 생성.

    제안만 생성하고 PENDING 상태로 저장한다. 절대 자동 적용 안 함.

    Returns:
        dict: rotation_proposal (있으면), None (레짐 미감지 또는 실패)
    """
    log("STEP 2b: 마켓 레짐 감지 (V6.0)")
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from run_paper_trading import _detect_market_regime, _generate_rotation_proposal

        regime_data = _detect_market_regime()
        regime      = regime_data.get('regime', 'UNKNOWN')
        log(f"  → 레짐={regime} | SPY_200MA={regime_data.get('spy_vs_200ma', 'N/A')}% "
            f"| QQQ_slope={regime_data.get('qqq_slope_5d', 'N/A')}% "
            f"| VIX={regime_data.get('vix_level', 'N/A')}")

        if regime == 'UNKNOWN':
            log(f"  레짐 미감지: {regime_data.get('error', '')}")
            return None

        proposal = _generate_rotation_proposal(regime_data)
        if proposal:
            log(f"  → 로테이션 제안 생성: {regime} → "
                f"US={proposal['proposal']['US_priority'][:2]}, "
                f"KR={proposal['proposal']['KR_priority'][:2]}")
        return proposal

    except Exception as e:
        log(f"  [오류] 레짐 감지 실패: {e}")
        return None


# ── Step 2d: V7.0 AI 운영 에이전트 ──────────────────────────────
def step_ai_ops(summary: dict) -> dict | None:
    """일일 리포트 생성 + 이상 감지 + 텔레그램 알림 (분석 전용, 거래 실행 금지).

    일 1회 실행 (매일 07:00 KST 기준 첫 실행 시). 이전에 오늘 리포트 생성됐으면 스킵.

    Returns:
        dict: AI 리포트, None이면 생략
    """
    # 오늘 이미 리포트 생성됐으면 스킵 (일 1회만)
    today = datetime.now().strftime('%Y-%m-%d')
    report_path = LOG_DIR / 'journal' / f'{today}-ai_report.json'
    if report_path.exists():
        log("STEP 2d: AI 운영 리포트 이미 생성됨 — 스킵")
        return None

    log("STEP 2d: AI 운영 에이전트 실행 (V7.0) — 분석 전용")
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from run_paper_trading import (_generate_daily_report, _detect_anomalies,
                                       _load_positions, _load_portfolio)

        pos_data  = _load_positions()
        portfolio = _load_portfolio()
        report    = _generate_daily_report(pos_data, portfolio)

        anomaly_count = len(report.get('anomalies', []))
        rec_count     = len(report.get('recommendations', []))
        log(f"  → 리포트 생성 완료 | 이상감지={anomaly_count}건 | 권고={rec_count}건")
        log(f"  → 저장: logs/journal/{today}-ai_report.json")

        # 텔레그램 AI 리포트 알림
        _send_ai_report_telegram(report)

        return report
    except Exception as e:
        log(f"  [오류] AI 운영 에이전트 실패: {e}")
        return None


def _send_ai_report_telegram(report: dict):
    """AI 일일 리포트 텔레그램 전송."""
    try:
        date_str  = report.get('date', '')
        summary   = report.get('summary', {})
        perf30    = report.get('performance', {}).get('30d', {})
        regime    = report.get('regime', {})
        anomalies = report.get('anomalies', [])
        recs      = report.get('recommendations', [])
        opens     = report.get('open_positions', [])

        lines = [
            f"🤖 <b>Warren AI 일일 리포트 [{date_str}]</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💼 포트폴리오: {summary.get('total_current_krw', 0):,.0f}원 "
            f"({summary.get('return_pct', 0):+.2f}%)",
            f"📊 누적: {summary.get('total_trades', 0)}건 | WR: {summary.get('win_rate', 0)}%",
        ]

        if perf30.get('trades', 0) > 0:
            lines.append(f"📈 30d: PF={perf30.get('profit_factor', 0)} | "
                         f"Exp={perf30.get('expectancy_krw', 0):+,.0f}원 | "
                         f"MDD={perf30.get('max_drawdown_pct', 0):.1f}%")

        regime_name = regime.get('regime', 'UNKNOWN')
        emoji = {'TRENDING': '🟢', 'SIDEWAYS': '🟡', 'RISK_OFF': '🔴'}.get(regime_name, '⚪')
        if regime_name != 'UNKNOWN':
            lines.append(f"{emoji} 레짐: {regime_name} | VIX={regime.get('vix_level', 'N/A')}")

        if opens:
            lines.append(f"📂 오픈: {len(opens)}개 — " +
                         ', '.join(f"{p['name'] or p['ticker']}({p['pnl_pct']:+.1f}%)"
                                   if p['pnl_pct'] is not None
                                   else p['name'] or p['ticker']
                                   for p in opens[:3]))

        if anomalies:
            lines.append(f"⚠️ 이상 감지 {len(anomalies)}건:")
            for a in anomalies[:3]:
                sev = '🔴' if a['severity'] == 'HIGH' else '🟡'
                lines.append(f"  {sev} {a['message']}")

        if recs:
            lines.append(f"💡 권고:")
            for r in recs[:3]:
                lines.append(f"  • {r}")

        _send_telegram('\n'.join(lines))
        log("  텔레그램 AI 리포트 전송 완료")
    except Exception as e:
        log(f"  텔레그램 AI 리포트 전송 실패: {e}")


# ── Step 2c: V6.2 동적 자본 배분 제안 ───────────────────────────
def step_capital_allocation(rotation: dict = None) -> dict | None:
    """성과 리포트 + 레짐 데이터 기반 자본 배분 제안 생성 (PENDING만).

    Returns:
        dict: 배분 제안, None이면 성과 데이터 부족
    """
    log("STEP 2c: 동적 자본 배분 제안 (V6.2)")
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from run_paper_trading import _generate_capital_allocation_proposal

        regime_data = rotation if rotation else {'regime': 'UNKNOWN'}
        proposal = _generate_capital_allocation_proposal(regime_data)
        if proposal:
            diff = proposal.get('diff_pct', {})
            log(f"  → 자본 배분 제안: KR{diff.get('KR',0):+}% / "
                f"US{diff.get('US',0):+}% / CRYPTO{diff.get('CRYPTO',0):+}%")
        else:
            log("  → 성과 데이터 부족 — 자본 배분 제안 생략")
        return proposal
    except Exception as e:
        log(f"  [오류] 자본 배분 제안 실패: {e}")
        return None


# ── Step 3: 텔레그램 알림 ─────────────────────────────────────────
def step_notify(summary: dict, proposals: list, is_proposal_run: bool,
                rotation: dict = None, alloc_proposal: dict = None):
    now = datetime.now().strftime('%H:%M KST')
    pnl_sign = '+' if summary.get('pnl', 0) >= 0 else ''

    # 기본 스캔 리포트 (매 스캔)
    msg_lines = [
        f"🤖 <b>Warren Bot v6.0</b> [{now}]",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📊 누적: {summary.get('trades', 0)}건 | WR: {summary.get('wr', 0)}%",
        f"💰 실현 손익: {pnl_sign}{summary.get('pnl', 0):,}원",
        f"📂 오픈: {summary.get('open', 0)}개",
    ]
    if summary.get('entries', 0):
        msg_lines.append(f"✅ 신규 진입: {summary['entries']}건")
    if summary.get('exits', 0):
        msg_lines.append(f"🔒 청산: {summary['exits']}건")

    # 레짐 정보 추가
    if rotation:
        regime = rotation.get('regime', 'UNKNOWN')
        vix    = rotation.get('regime_data', {}).get('vix_level', 'N/A')
        spy_vs = rotation.get('regime_data', {}).get('spy_vs_200ma', 'N/A')
        regime_emoji = {'TRENDING': '🟢', 'SIDEWAYS': '🟡', 'RISK_OFF': '🔴'}.get(regime, '⚪')
        msg_lines.append(f"{regime_emoji} 레짐: {regime} | VIX={vix} | SPY_200MA={spy_vs:+}%")

    _send_telegram('\n'.join(msg_lines))

    # 전략 제안 알림 (학습 제안 있을 때)
    if proposals and is_proposal_run:
        prop_lines = [
            "⚠️ <b>전략 수정 제안 (승인 필요)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for i, p in enumerate(proposals[:5], 1):
            prop_lines.append(f"{i}. [{p['type']}] {p.get('item','')}")
            prop_lines.append(f"   → {p.get('reason','')}")
        prop_lines.append("")
        prop_lines.append("🔒 자동 적용 금지 — strategy_registry 자동 수정 불가")
        prop_lines.append("📋 Manual approval required")
        prop_lines.append("⚠️ Claude Code에서 논의 후 수동 승인 필요")
        _send_telegram('\n'.join(prop_lines))
        log("  텔레그램 제안 알림 전송 완료")

    # 로테이션 제안 알림 (레짐 변경 감지 시)
    if rotation:
        r_proposal = rotation.get('proposal', {})
        rot_lines = [
            f"🔄 <b>전략 로테이션 제안 [V6.0]</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"레짐: {rotation.get('regime')}",
            f"이유: {r_proposal.get('reason', '')}",
            f"US 우선순위: {' → '.join(r_proposal.get('US_priority', [])[:3])}",
            f"KR 우선순위: {' → '.join(r_proposal.get('KR_priority', [])[:3])}",
            f"CRYPTO: {'정상' if r_proposal.get('CRYPTO_priority') else '신규진입 자제 권고'}",
            f"",
            f"🔒 자동 적용 금지",
            f"📋 Manual approval required",
            f"⚠️ Claude Code에서 논의 후 수동 승인",
        ]
        _send_telegram('\n'.join(rot_lines))
        log("  텔레그램 로테이션 제안 알림 전송 완료")

    # 자본 배분 제안 알림 (V6.2)
    if alloc_proposal:
        curr  = alloc_proposal.get('current_alloc', {})
        prop  = alloc_proposal.get('proposed_alloc', {})
        diff  = alloc_proposal.get('diff_pct', {})
        alloc_lines = [
            f"💰 <b>자본 배분 제안 [V6.2]</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"레짐: {alloc_proposal.get('regime')}",
            f"현재 → 제안 (변화)",
            f"  KR:     {curr.get('KR',0)}% → {prop.get('KR',0)}% ({diff.get('KR',0):+}%)",
            f"  US:     {curr.get('US',0)}% → {prop.get('US',0)}% ({diff.get('US',0):+}%)",
            f"  CRYPTO: {curr.get('CRYPTO',0)}% → {prop.get('CRYPTO',0)}% ({diff.get('CRYPTO',0):+}%)",
            f"",
            f"🔒 자동 적용 금지",
            f"📋 INITIAL_CAPITAL 수동 수정 필요",
        ]
        _send_telegram('\n'.join(alloc_lines))
        log("  텔레그램 자본 배분 제안 알림 전송 완료")


# ── 메인 ─────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log(f"Warren Master Loop v7.0 시작 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

    # Step 1: 트레이딩
    summary = step_paper_trading()

    # Step 2: 학습 (10건마다)
    trade_count     = _trade_count()
    proposals       = step_learning(trade_count)
    is_proposal_run = bool(proposals)

    # 제안 있으면 잠금 저장
    if proposals:
        _save_proposal(proposals)

    # Step 2b: 레짐 감지 + 전략 로테이션 제안 (V6.0/6.1)
    rotation = step_regime_rotation()
    if rotation:
        _save_proposal([{
            'type':   'STRATEGY_ROTATION',
            'item':   f"레짐={rotation['regime']}",
            'reason': rotation['proposal'].get('reason', ''),
            'effect': f"US:{rotation['proposal']['US_priority'][:2]} KR:{rotation['proposal']['KR_priority'][:2]}",
            'status': 'PENDING',
            'detail': rotation,
        }])

    # Step 2c: 동적 자본 배분 제안 (V6.2)
    alloc_proposal = step_capital_allocation(rotation)
    if alloc_proposal:
        _save_proposal([{
            'type':   'CAPITAL_ALLOCATION',
            'item':   f"레짐={alloc_proposal['regime']}",
            'reason': f"시장별 30d 성과 기반 재배분 제안",
            'effect': (f"KR:{alloc_proposal['diff_pct'].get('KR',0):+}% "
                       f"US:{alloc_proposal['diff_pct'].get('US',0):+}% "
                       f"CRYPTO:{alloc_proposal['diff_pct'].get('CRYPTO',0):+}%"),
            'status': 'PENDING',
            'detail': alloc_proposal,
        }])

    # Step 2d: AI 운영 에이전트 (V7.0) — 일 1회 리포트 + 이상 감지
    step_ai_ops(summary)

    # Step 3: 텔레그램
    step_notify(summary, proposals, is_proposal_run, rotation=rotation,
                alloc_proposal=alloc_proposal)

    log("Warren Master Loop 완료")
    log("=" * 60)


if __name__ == '__main__':
    main()
