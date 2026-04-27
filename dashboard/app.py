# -*- coding: utf-8 -*-
"""Warren FVG+OB Trading Dashboard"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="Warren Trading Bot",
    page_icon="W",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    section[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
    .metric-card {
        background: linear-gradient(135deg, #1c2128, #21262d);
        border: 1px solid #30363d; border-radius: 12px;
        padding: 20px; text-align: center; margin: 6px 0;
    }
    .metric-value { font-size: 26px; font-weight: 700; }
    .metric-label { font-size: 12px; color: #8b949e; margin-top: 6px; }
    .positive { color: #3fb950; }
    .negative { color: #f85149; }
    .neutral  { color: #e3b341; }
    div[data-testid="stMetric"] { background:#1c2128; border-radius:8px; padding:12px; border:1px solid #30363d; }
    .stButton>button { background:#238636; color:white; border:none; border-radius:6px; font-weight:600; }
    .stButton>button:hover { background:#2ea043; }
    .stDataFrame { border-radius:8px; }
    h1,h2,h3,h4 { color: #e6edf3; }
    .signal-buy { background:#238636; color:white; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
    .signal-flat { background:#30363d; color:#8b949e; padding:3px 10px; border-radius:12px; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:16px 0 8px 0;'>
    <div style='font-size:20px;font-weight:700;color:#3fb950;'>Warren Bot</div>
    <div style='font-size:11px;color:#8b949e;'>FVG+OB Auto Trader v2.0</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    page = st.radio("", [
        "Overview",
        "FVG+OB 신호",
        "Market Brain",
        "Strategy Factory",
        "Backtest Results",
        "Asset Analysis",
        "Trade Log",
        "Settings",
    ], label_visibility="collapsed")

    st.markdown("---")
    st.markdown("**API 연결**")
    st.markdown("🟢 KIS 모의투자")
    st.markdown("🟢 업비트")
    st.markdown("🔴 빗썸")
    st.markdown("---")
    st.markdown(f"<div style='font-size:11px;color:#8b949e;'>업데이트: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    if st.button("새로고침"):
        st.rerun()

# ── 페이지 라우팅 ─────────────────────────────────────────────
if page == "Overview":
    from dashboard.pages import page_overview
    page_overview.render()

elif page == "FVG+OB 신호":
    from dashboard.pages import page_signals
    page_signals.render()

elif page == "Market Brain":
    from dashboard.pages import page_brain
    page_brain.render()

elif page == "Strategy Factory":
    from dashboard.pages import page_strategy
    page_strategy.render()

elif page == "Backtest Results":
    from dashboard.pages import page_backtest
    page_backtest.render()

elif page == "Asset Analysis":
    from dashboard.pages import page_analysis
    page_analysis.render()

elif page == "Trade Log":
    from dashboard.pages import page_trades
    page_trades.render()

elif page == "Settings":
    from dashboard.pages import page_settings
    page_settings.render()
