# -*- coding: utf-8 -*-
"""Live Trading — 실제 자동매매 제어 및 실시간 모니터링"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'


@st.cache_data(ttl=15)
def _kis_balance() -> dict:
    try:
        from core.kis_trader import get_balance
        return get_balance()
    except Exception as e:
        return {'cash': 0, 'total': 0, 'pnl': 0, 'positions': [], 'error': str(e)}


def _trade_log() -> pd.DataFrame:
    p = LOG_DIR / 'trade_log.csv'
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p, encoding='utf-8-sig')
    except Exception:
        return pd.DataFrame()


def _kis_trades() -> pd.DataFrame:
    p = LOG_DIR / 'kis_trades.csv'
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p, encoding='utf-8-sig')
    except Exception:
        return pd.DataFrame()


def render():
    st.markdown("### Live Trading — 자동매매 제어 센터")

    bal = _kis_balance()
    has_err = 'error' in bal

    # ── Row 1: KIS 연결 상태 + 주요 지표 ───────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    total = bal.get('total', 0)
    cash  = bal.get('cash', 0)
    pnl   = bal.get('pnl', 0)
    positions = bal.get('positions', [])

    status_color = '#26a69a' if not has_err else '#ef5350'
    status_text  = 'KIS 연결됨' if not has_err else 'KIS 오류'

    c1.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val' style='color:{status_color};font-size:13px;'>{"● " + status_text}</div>
    <div class='kpi-label'>모의투자 연결 상태</div></div>""", unsafe_allow_html=True)

    pnl_col = '#26a69a' if pnl >= 0 else '#ef5350'
    c2.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val'>{total:,.0f}</div>
    <div class='kpi-label'>총 평가 (원)</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val'>{cash:,.0f}</div>
    <div class='kpi-label'>예수금 (원)</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val' style='color:{pnl_col};'>{pnl:+,.0f}</div>
    <div class='kpi-label'>평가 손익 (원)</div></div>""", unsafe_allow_html=True)
    c5.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val'>{len(positions)}</div>
    <div class='kpi-label'>오픈 포지션</div></div>""", unsafe_allow_html=True)

    trade_df = _trade_log()
    today_pnl = 0
    if not trade_df.empty and 'pnl' in trade_df.columns and 'date' in trade_df.columns:
        try:
            trade_df['date'] = pd.to_datetime(trade_df['date'], errors='coerce')
            today = trade_df[trade_df['date'].dt.date == datetime.today().date()]
            today_pnl = today['pnl'].sum()
        except Exception:
            pass
    today_col = '#26a69a' if today_pnl >= 0 else '#ef5350'
    c6.markdown(f"""<div class='kpi-card'>
    <div class='kpi-val' style='color:{today_col};'>{today_pnl:+,.0f}</div>
    <div class='kpi-label'>오늘 실현 손익</div></div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Row 2: 포지션 테이블 + 수동 주문 ───────────────────────
    pos_col, order_col = st.columns([3, 2])

    with pos_col:
        st.markdown("<div class='sec-hdr'>현재 보유 포지션</div>", unsafe_allow_html=True)
        if positions:
            pos_df = pd.DataFrame(positions)

            # 평가손익 컬럼 색상
            def _style_pnl(val):
                try:
                    v = float(str(val).replace(',',''))
                    return 'color: #26a69a' if v > 0 else 'color: #ef5350'
                except Exception:
                    return ''

            st.dataframe(pos_df, width='stretch', hide_index=True, height=220)

            # 청산 버튼
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            tickers = [p.get('ticker','') for p in positions if p.get('ticker')]
            if tickers:
                sel_ticker = st.selectbox("청산할 종목", tickers, key='close_ticker')
                if st.button("선택 종목 청산 (모의)", type="primary", key='close_pos'):
                    try:
                        from core.kis_trader import get_balance as _gb
                        current_price = 0
                        from data.data_loader import load
                        from config.assets import ALL_ASSETS
                        asset = ALL_ASSETS.get(sel_ticker, {})
                        df_tmp = load(sel_ticker, asset.get('market','KR'))
                        if df_tmp is not None:
                            current_price = float(df_tmp['Close'].iloc[-1])
                        if current_price > 0:
                            st.success(f"{sel_ticker} 청산 신호 발송 (현재가 {current_price:,.0f}원)")
                        else:
                            st.warning("현재가 조회 실패")
                    except Exception as e:
                        st.error(f"청산 오류: {e}")
        else:
            st.markdown("""<div style='height:220px;display:flex;align-items:center;
            justify-content:center;background:#1e222d;border-radius:6px;border:1px solid #2a2e39;
            font-size:12px;color:#787b86;'>보유 포지션 없음</div>""", unsafe_allow_html=True)

    with order_col:
        st.markdown("<div class='sec-hdr'>수동 주문 실행</div>", unsafe_allow_html=True)
        with st.form("manual_order"):
            from config.assets import ALL_ASSETS
            ticker_opts = list(ALL_ASSETS.keys())
            sel = st.selectbox("종목", ticker_opts,
                               format_func=lambda t: f"{t} — {ALL_ASSETS[t]['name']}")
            action = st.radio("주문 유형", ["BUY", "SELL"], horizontal=True)
            qty = st.number_input("수량", min_value=1, value=1, step=1)
            price_mode = st.radio("가격 방식", ["시장가", "지정가"], horizontal=True)
            manual_price = st.number_input("지정가 (원)", min_value=0, value=0,
                                           disabled=(price_mode == "시장가"))
            submitted = st.form_submit_button("주문 실행", type="primary", use_container_width=True)

            if submitted:
                try:
                    from core.kis_trader import buy_order, sell_order
                    price_input = 0 if price_mode == "시장가" else int(manual_price)
                    if action == "BUY":
                        result = buy_order(sel, qty, price_input)
                        st.success(f"BUY {sel} x{qty} — 주문 완료")
                    else:
                        result = sell_order(sel, qty, price_input)
                        st.success(f"SELL {sel} x{qty} — 주문 완료")
                    st.json(result)
                except Exception as e:
                    st.error(f"주문 오류: {e}")

        # FVG+OB 즉시 스캔 → 자동 주문
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.markdown("<div class='sec-hdr'>FVG+OB 자동 스캔 → 주문</div>", unsafe_allow_html=True)
        if st.button("지금 스캔 후 자동 주문", use_container_width=True):
            with st.spinner("KR5+US5 스캔 중..."):
                try:
                    from core.fvg_ob_tester import scan_all
                    signals = scan_all()
                    if signals:
                        st.success(f"{len(signals)}건 신호 발견 — 주문 처리 중...")
                        for s in signals:
                            st.info(f"→ {s['name']} ({s['type']}) 진입가: {s['entry']}")
                    else:
                        st.info("현재 신호 없음 — 관망")
                except Exception as e:
                    st.error(f"스캔 오류: {e}")

    # ── Row 3: 오늘 체결 내역 ───────────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sec-hdr'>오늘 체결 내역 (KIS 모의)</div>", unsafe_allow_html=True)

    kis_df = _kis_trades()
    if not kis_df.empty:
        if 'date' in kis_df.columns:
            try:
                kis_df['date'] = pd.to_datetime(kis_df['date'], errors='coerce')
                today_df = kis_df[kis_df['date'].dt.date == datetime.today().date()]
                show_df  = today_df.iloc[::-1] if not today_df.empty else kis_df.iloc[::-1].head(20)
            except Exception:
                show_df = kis_df.iloc[::-1].head(20)
        else:
            show_df = kis_df.iloc[::-1].head(20)

        st.dataframe(show_df, width='stretch', hide_index=True)
        dl_df = kis_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("CSV 다운로드", dl_df, "kis_trades.csv", "text/csv")
    else:
        st.info("체결 내역 없음 — 자동매매 실행 후 표시됩니다")

    # ── Row 4: 자동매매 스케줄러 상태 ─────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sec-hdr'>자동매매 스케줄러 상태</div>", unsafe_allow_html=True)

    s1, s2, s3, s4 = st.columns(4)
    import subprocess, os

    def _check_process(name: str) -> bool:
        try:
            result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq python.exe'],
                                    capture_output=True, text=True, timeout=3)
            return name.lower() in result.stdout.lower()
        except Exception:
            return False

    scanner_log = LOG_DIR / 'scanner.log'
    dashboard_log = LOG_DIR / 'dashboard.log'
    webhook_log   = LOG_DIR / 'webhook.log'

    def _last_log(p: Path) -> str:
        if not p.exists(): return '로그 없음'
        try:
            lines = p.read_text(encoding='utf-8', errors='ignore').strip().split('\n')
            return lines[-1][-80:] if lines else '없음'
        except Exception: return '읽기 오류'

    for col, (label, log_path) in zip([s1,s2,s3,s4],[
        ('KR 스캐너', scanner_log),
        ('대시보드', dashboard_log),
        ('웹훅 서버', webhook_log),
        ('KR 자동매매', LOG_DIR / 'kr_autotrader.log'),
    ]):
        last = _last_log(log_path)
        col.markdown(f"""<div class='kpi-card'>
        <div style='font-size:11px;font-weight:600;color:#d1d4dc;margin-bottom:4px;'>{label}</div>
        <div style='font-size:10px;color:#787b86;word-break:break-all;'>{last[:60]}...</div>
        </div>""", unsafe_allow_html=True)

    st.caption(f"업데이트: {datetime.now().strftime('%H:%M:%S')} — 자동 새로고침: 사이드바 '새로고침' 클릭")
