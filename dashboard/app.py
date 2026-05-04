# -*- coding: utf-8 -*-
"""Warren Trading Bot — Professional Dashboard v4.0"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime
import pytz

st.set_page_config(
    page_title="Warren Bot",
    page_icon="W",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design System (TradingView-inspired) ──────────────────────────
st.markdown("""
<style>
  /* ─ Reset & Base ─ */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; font-size: 13px; }
  .stApp { background: #131722; color: #d1d4dc; }

  /* ─ Sidebar ─ */
  section[data-testid="stSidebar"] {
    background: #1e222d;
    border-right: 1px solid #363a45;
    width: 200px !important;
  }
  section[data-testid="stSidebar"] .block-container { padding: 8px 0; }

  /* ─ Main container ─ */
  .block-container { padding: 0 16px 16px 16px !important; max-width: 100% !important; }

  /* ─ Headings ─ */
  h1 { font-size: 16px !important; font-weight: 700 !important; color: #d1d4dc !important; margin: 0 0 8px 0 !important; }
  h2 { font-size: 14px !important; font-weight: 600 !important; color: #d1d4dc !important; margin: 0 0 6px 0 !important; }
  h3 { font-size: 13px !important; font-weight: 600 !important; color: #d1d4dc !important; margin: 0 0 4px 0 !important; }

  /* ─ Metric Cards (custom) ─ */
  .kpi-card {
    background: #1e222d;
    border: 1px solid #2a2e39;
    border-radius: 6px;
    padding: 10px 12px;
    margin: 3px 0;
  }
  .kpi-val { font-size: 18px; font-weight: 700; line-height: 1.2; }
  .kpi-label { font-size: 11px; color: #787b86; margin-top: 2px; }
  .kpi-delta { font-size: 11px; margin-top: 1px; }

  /* ─ Native st.metric override ─ */
  div[data-testid="stMetric"] {
    background: #1e222d;
    border: 1px solid #2a2e39;
    border-radius: 6px;
    padding: 8px 12px !important;
  }
  div[data-testid="stMetricLabel"] { font-size: 11px !important; color: #787b86 !important; }
  div[data-testid="stMetricValue"] { font-size: 18px !important; font-weight: 700 !important; color: #d1d4dc !important; }
  div[data-testid="stMetricDelta"] { font-size: 11px !important; }

  /* ─ DataFrames ─ */
  .stDataFrame { border-radius: 6px; font-size: 12px !important; }
  .stDataFrame table { font-size: 12px !important; }

  /* ─ Tabs ─ */
  .stTabs [data-baseweb="tab-list"] {
    background: #1e222d;
    border-radius: 6px 6px 0 0;
    border-bottom: 1px solid #2a2e39;
    gap: 0;
  }
  .stTabs [data-baseweb="tab"] {
    font-size: 12px !important;
    padding: 6px 14px !important;
    color: #787b86;
    border-radius: 0;
    border: none;
  }
  .stTabs [aria-selected="true"] {
    color: #d1d4dc !important;
    border-bottom: 2px solid #2962ff !important;
    background: transparent !important;
  }
  .stTabs [data-baseweb="tab-panel"] {
    background: #1e222d;
    border: 1px solid #2a2e39;
    border-top: none;
    border-radius: 0 0 6px 6px;
    padding: 12px;
  }

  /* ─ Buttons ─ */
  .stButton > button {
    background: #2962ff;
    color: #fff;
    border: none;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
    height: 30px;
  }
  .stButton > button:hover { background: #1e4fd8; }

  /* ─ Selectbox / Input ─ */
  .stSelectbox label, .stTextInput label, .stNumberInput label { font-size: 11px !important; color: #787b86 !important; }
  .stSelectbox [data-baseweb="select"] { background: #2a2e39; border: 1px solid #363a45; border-radius: 4px; font-size: 12px; }
  .stTextInput input, .stNumberInput input {
    background: #2a2e39 !important;
    border: 1px solid #363a45 !important;
    color: #d1d4dc !important;
    font-size: 12px !important;
    padding: 4px 8px !important;
  }

  /* ─ Divider ─ */
  hr { border-color: #2a2e39 !important; margin: 8px 0 !important; }

  /* ─ Expander ─ */
  .streamlit-expanderHeader { font-size: 12px !important; background: #1e222d !important; }

  /* ─ Info / Warning / Error ─ */
  .stAlert { font-size: 12px !important; padding: 8px 12px !important; }

  /* ─ Spinner ─ */
  .stSpinner { font-size: 12px !important; }

  /* ─ Hide auto-generated sidebar page list ─ */
  section[data-testid="stSidebarNav"],
  div[data-testid="stSidebarNavItems"],
  div[data-testid="collapsedControl"] { display: none !important; }

  /* ─ Scrollbar ─ */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #131722; }
  ::-webkit-scrollbar-thumb { background: #363a45; border-radius: 3px; }

  /* ─ Status badges ─ */
  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.3px;
  }
  .badge-live  { background: rgba(38,166,154,.2); color: #26a69a; border: 1px solid rgba(38,166,154,.4); }
  .badge-paper { background: rgba(255,183,77,.2); color: #ffb74d; border: 1px solid rgba(255,183,77,.4); }
  .badge-off   { background: rgba(120,123,134,.15); color: #787b86; border: 1px solid rgba(120,123,134,.3); }
  .badge-buy   { background: rgba(38,166,154,.2); color: #26a69a; }
  .badge-sell  { background: rgba(239,83,80,.2); color: #ef5350; }

  /* ─ Section header ─ */
  .sec-hdr {
    font-size: 11px;
    font-weight: 600;
    color: #787b86;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 0 0 6px 0;
    border-bottom: 1px solid #2a2e39;
    margin-bottom: 8px;
  }

  /* ─ Sidebar nav ─ */
  .nav-item {
    display: block;
    padding: 7px 16px;
    font-size: 12px;
    color: #787b86;
    cursor: pointer;
    border-left: 2px solid transparent;
    transition: all .15s;
  }
  .nav-item:hover { color: #d1d4dc; background: rgba(255,255,255,.04); }
  .nav-item.active { color: #d1d4dc; border-left-color: #2962ff; background: rgba(41,98,255,.1); }

  /* ─ Top bar ─ */
  .top-bar {
    background: #1e222d;
    border-bottom: 1px solid #2a2e39;
    padding: 5px 16px;
    margin: -16px -16px 12px -16px;
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 11px;
    color: #787b86;
  }
  .mkt-pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600;
  }
  .mkt-open   { background: rgba(38,166,154,.15); color: #26a69a; }
  .mkt-closed { background: rgba(120,123,134,.12); color: #787b86; }
  .mkt-pre    { background: rgba(255,183,77,.15);  color: #ffb74d; }

  /* ─ P&L colors ─ */
  .pos { color: #26a69a !important; }
  .neg { color: #ef5350 !important; }
  .neu { color: #787b86 !important; }
</style>
""", unsafe_allow_html=True)

# ── Market Hours Helper ────────────────────────────────────────────
def _market_status() -> dict:
    kst = pytz.timezone('Asia/Seoul')
    est = pytz.timezone('America/New_York')
    now_kst = datetime.now(kst)
    now_est = datetime.now(est)

    kr_open  = now_kst.weekday() < 5 and 9 <= now_kst.hour < 15 and not (now_kst.hour == 14 and now_kst.minute >= 30)
    us_open  = now_est.weekday() < 5 and 9 <= now_est.hour < 16 and not (now_est.hour == 9 and now_est.minute < 30)
    us_pre   = now_est.weekday() < 5 and 4 <= now_est.hour < 9
    return {
        'kr':     'open'   if kr_open else 'closed',
        'us':     'open'   if us_open else ('pre' if us_pre else 'closed'),
        'crypto': 'open',
        'kst':    now_kst.strftime('%H:%M:%S KST'),
        'est':    now_est.strftime('%H:%M EST'),
    }


# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:12px 16px 8px;border-bottom:1px solid #2a2e39;margin-bottom:8px;'>
      <div style='font-size:15px;font-weight:700;color:#d1d4dc;'>W Warren Bot</div>
      <div style='font-size:10px;color:#787b86;margin-top:2px;'>Multi-Strategy v5.0 | CB-1.5% MDD-10%</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("Navigation", [
        "Overview",
        "Paper Trading",
        "투자일지",
        "FVG+OB Signals",
        "Market Brain",
        "Backtest Results",
        "Live Trading",
        "Trade Log",
        "시스템 문서",
        "Settings",
    ], label_visibility="collapsed")

    # Portfolio mini-summary
    st.markdown("""<div style='padding:8px 16px;margin-top:8px;border-top:1px solid #2a2e39;'>
    <div class='sec-hdr' style='margin-bottom:6px;'>PORTFOLIO</div>
    """, unsafe_allow_html=True)

    try:
        from core.kis_trader import get_balance
        bal = get_balance()
        cash = bal.get('cash', 0)
        total = bal.get('total', 0)
        pnl   = bal.get('pnl', 0)
        pnl_color = '#26a69a' if pnl >= 0 else '#ef5350'
        st.markdown(f"""
        <div style='font-size:11px;color:#787b86;margin-bottom:2px;'>총 평가</div>
        <div style='font-size:16px;font-weight:700;color:#d1d4dc;margin-bottom:4px;'>{total:,.0f}원</div>
        <div style='font-size:11px;color:{pnl_color};'>손익 {pnl:+,.0f}원</div>
        <div style='font-size:11px;color:#787b86;margin-top:4px;'>예수금 {cash:,.0f}원</div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""<div style='font-size:11px;color:#787b86;'>KIS 미연결</div>""",
                    unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # API status
    st.markdown("""<div style='padding:8px 16px;border-top:1px solid #2a2e39;'>
    <div class='sec-hdr' style='margin-bottom:6px;'>API STATUS</div>
    """, unsafe_allow_html=True)

    def _api_dot(ok): return "🟢" if ok else "🔴"
    try:
        from core.kis_trader import get_balance as _kb; _kb(); kis_ok = True
    except Exception: kis_ok = False
    try:
        import os; upbit_ok = bool(os.getenv('UPBIT_ACCESS_KEY',''))
    except Exception: upbit_ok = False

    st.markdown(f"""
    <div style='font-size:11px;line-height:2;'>
    {_api_dot(kis_ok)} KIS 모의투자<br>
    {_api_dot(upbit_ok)} 업비트<br>
    🔴 빗썸
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Clock + refresh
    mkt = _market_status()
    st.markdown(f"""<div style='padding:8px 16px;border-top:1px solid #2a2e39;font-size:10px;color:#787b86;'>
    {mkt['kst']}<br>{mkt['est']}
    </div>""", unsafe_allow_html=True)

    if st.button("새로고침", use_container_width=True):
        st.rerun()

    # ── 저널 갱신 트리거 감지 (07:00/17:00/21:00 자동 반영) ──────
    import json as _json
    _trigger = Path(__file__).parent.parent / 'logs' / 'dashboard_refresh.json'
    _last_refresh = st.session_state.get('_last_dashboard_refresh', '')
    if _trigger.exists():
        try:
            _t = _json.loads(_trigger.read_text(encoding='utf-8'))
            _updated = _t.get('last_updated', '')
            if _updated and _updated != _last_refresh:
                st.session_state['_last_dashboard_refresh'] = _updated
                _session_label = {'morning':'아침브리핑','afternoon':'KR마감복기','evening':'전체복기'}.get(_t.get('session',''), '업데이트')
                st.success(f"📋 {_session_label} 완료 — 대시보드 자동 갱신 ({_updated})")
                st.rerun()
        except Exception:
            pass

# ── Top Status Bar ────────────────────────────────────────────────
mkt = _market_status()
def _mkt_pill(label, status):
    cls = {'open':'mkt-open','closed':'mkt-closed','pre':'mkt-pre'}.get(status,'mkt-closed')
    dot = {'open':'●','closed':'○','pre':'◐'}.get(status,'○')
    return f"<span class='mkt-pill {cls}'>{dot} {label}</span>"

_journal_updated = ''
try:
    import json as _json2
    _tr2 = Path(__file__).parent.parent / 'logs' / 'dashboard_refresh.json'
    if _tr2.exists():
        _td = _json2.loads(_tr2.read_text(encoding='utf-8'))
        _session_kor = {'morning':'07:00 아침브리핑','afternoon':'17:00 KR마감복기','evening':'21:00 전체복기'}.get(_td.get('session',''), '업데이트')
        _journal_updated = f' | 📋 {_session_kor} {_td.get("last_updated","")}'
except Exception:
    pass

st.markdown(f"""
<div class='top-bar'>
  <span style='color:#d1d4dc;font-weight:600;font-size:12px;'>Warren Trading Bot</span>
  <span style='color:#2a2e39;'>|</span>
  {_mkt_pill('KR',mkt['kr'])}
  {_mkt_pill('US',mkt['us'])}
  {_mkt_pill('CRYPTO',mkt['crypto'])}
  <span style='margin-left:auto;font-size:11px;color:#787b86;'>{_journal_updated}</span>
  <span style='color:#d1d4dc;font-size:12px;margin-left:12px;'>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
</div>
""", unsafe_allow_html=True)

# ── Page Routing ──────────────────────────────────────────────────
if page == "Overview":
    from dashboard._pages import _page_overview as _po; _po.render()
elif page == "Paper Trading":
    from dashboard._pages import _page_paper as _ppt; _ppt.render()
elif page == "투자일지":
    from dashboard._pages import _page_journal as _pj; _pj.show()
elif page == "FVG+OB Signals":
    from dashboard._pages import _page_signals as _ps; _ps.render()
elif page == "Market Brain":
    from dashboard._pages import _page_brain as _pb; _pb.render()
elif page == "Backtest Results":
    from dashboard._pages import _page_backtest as _pbk; _pbk.render()
elif page == "Live Trading":
    from dashboard._pages import _page_live as _pl; _pl.render()
elif page == "Trade Log":
    from dashboard._pages import _page_trades as _ptr; _ptr.render()
elif page == "시스템 문서":
    from dashboard._pages import _page_docs as _pdc; _pdc.render()
elif page == "Settings":
    from dashboard._pages import _page_settings as _pse; _pse.render()
