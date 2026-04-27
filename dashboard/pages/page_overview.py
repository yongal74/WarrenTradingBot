# -*- coding: utf-8 -*-
"""Overview — KIS 모의투자 잔고 + FVG+OB 실시간 신호"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'

def _get_kis_balance():
    try:
        from core.kis_trader import get_balance
        return get_balance()
    except Exception as e:
        return {'cash': 0, 'total': 0, 'pnl': 0, 'positions': [], 'error': str(e)}

def _get_signals():
    try:
        from core.fvg_ob_tester import scan_all
        return scan_all()
    except Exception as e:
        return []

def _get_signal_log():
    path = LOG_DIR / 'forward_signals.csv'
    if not path.exists(): return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        return df
    except: return pd.DataFrame()

def _get_kis_trades():
    path = LOG_DIR / 'kis_trades.csv'
    if not path.exists(): return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        return df
    except: return pd.DataFrame()

def render():
    st.markdown("""
    <div style='background:linear-gradient(90deg,#238636,#1a7f37);border-radius:10px;
    padding:16px 24px;margin-bottom:20px;'>
    <span style='font-size:22px;font-weight:700;color:white;'>Warren FVG+OB Trading Bot</span><br>
    <span style='font-size:13px;color:#b3f0c5;'>KR 한국장 | US 미국장 | CRYPTO 코인 — 모의투자</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 자본 배분 현황 ─────────────────────────────────────────
    st.markdown("#### 자본 배분")
    c1, c2, c3, c4 = st.columns(4)
    allocations = [
        ('한국장 (KR)', 2_400_000, '#3fb950'),
        ('미국장 (US)', 1_200_000, '#58a6ff'),
        ('코인 (CRYPTO)', 2_400_000, '#e3b341'),
        ('총 시드', 6_000_000, '#8b949e'),
    ]
    for col, (label, amt, color) in zip([c1,c2,c3,c4], allocations):
        with col:
            st.markdown(f"""<div class='metric-card'>
            <div class='metric-value' style='color:{color}'>{amt:,}</div>
            <div class='metric-label'>{label} (원)</div></div>""",
            unsafe_allow_html=True)

    st.markdown("---")

    # ── KIS 모의투자 잔고 ──────────────────────────────────────
    st.markdown("#### KIS 모의투자 잔고")
    with st.spinner('KIS 잔고 조회 중...'):
        bal = _get_kis_balance()

    if 'error' not in bal:
        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(f"""<div class='metric-card'>
            <div class='metric-value'>{bal['cash']:,}</div>
            <div class='metric-label'>예수금 (원)</div></div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class='metric-card'>
            <div class='metric-value'>{bal['total']:,}</div>
            <div class='metric-label'>총 평가 (원)</div></div>""", unsafe_allow_html=True)
        with k3:
            color = 'positive' if bal['pnl'] >= 0 else 'negative'
            st.markdown(f"""<div class='metric-card'>
            <div class='metric-value {color}'>{bal['pnl']:+,}</div>
            <div class='metric-label'>평가 손익 (원)</div></div>""", unsafe_allow_html=True)

        if bal.get('positions'):
            st.markdown("**보유 종목**")
            pos_df = pd.DataFrame(bal['positions'])
            st.dataframe(pos_df, use_container_width=True, hide_index=True)
        else:
            st.info("현재 보유 종목 없음")
    else:
        st.warning(f"KIS 연결 오류: {bal['error']}")

    st.markdown("---")

    # ── FVG+OB 실시간 신호 ────────────────────────────────────
    col_sig, col_log = st.columns([1, 1])

    with col_sig:
        st.markdown("#### FVG+OB 실시간 신호 스캔")
        if st.button("🔍 지금 스캔"):
            with st.spinner('KR5 + US5 스캔 중...'):
                signals = _get_signals()
            if signals:
                sig_df = pd.DataFrame(signals)
                st.success(f"{len(signals)}건 신호 발생!")
                display_cols = ['name','ticker','market','type','price','entry','tp_pct','sl_pct']
                display_cols = [c for c in display_cols if c in sig_df.columns]
                st.dataframe(sig_df[display_cols], use_container_width=True, hide_index=True)
            else:
                st.info("현재 신호 없음 — 관망")
        else:
            st.info("'지금 스캔' 버튼을 눌러 실시간 신호를 확인하세요")

    with col_log:
        st.markdown("#### 누적 신호 로그")
        log_df = _get_signal_log()
        if not log_df.empty:
            st.markdown(f"**총 {len(log_df)}건 누적**")
            st.dataframe(log_df.tail(20).iloc[::-1], use_container_width=True, hide_index=True)

            # 시장별 신호 분포
            if 'market' in log_df.columns:
                mkt_cnt = log_df['market'].value_counts()
                fig = go.Figure(go.Bar(
                    x=mkt_cnt.index, y=mkt_cnt.values,
                    marker_color=['#3fb950','#58a6ff','#e3b341'],
                ))
                fig.update_layout(
                    height=200, paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(13,17,23,0.8)',
                    font_color='#e6edf3', showlegend=False,
                    margin=dict(t=10,b=30,l=40,r=10),
                    title='시장별 신호 건수',
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("신호 로그 없음 — 포워드 테스터 실행 필요")

    st.markdown("---")

    # ── KIS 체결 내역 ─────────────────────────────────────────
    st.markdown("#### KIS 모의투자 체결 내역")
    kis_df = _get_kis_trades()
    if not kis_df.empty:
        st.dataframe(kis_df.iloc[::-1].head(50), use_container_width=True, hide_index=True)
        st.download_button("CSV 다운로드", kis_df.to_csv(index=False).encode('utf-8-sig'),
                           "kis_trades.csv", "text/csv")
    else:
        st.info("아직 체결 내역 없음 — 자동매매 실행 후 표시됩니다")

    # 업데이트 시각
    st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
