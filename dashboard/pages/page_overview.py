# -*- coding: utf-8 -*-
"""Overview — Mission Control (st.metric 네이티브, 완전 다크모드)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'


@st.cache_data(ttl=30)
def _kis_balance() -> dict:
    try:
        from core.kis_trader import get_balance
        return get_balance()
    except Exception as e:
        return {'cash': 0, 'total': 0, 'pnl': 0, 'positions': [], 'error': str(e)}


def _load_csv(name: str) -> pd.DataFrame:
    p = LOG_DIR / name
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, encoding='utf-8-sig')
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


def render():
    bal      = _kis_balance()
    sig_df   = _load_csv('forward_signals.csv')
    trade_df = _load_csv('trade_log.csv')

    total     = bal.get('total', 0)
    cash      = bal.get('cash', 0)
    pnl       = bal.get('pnl', 0)
    positions = bal.get('positions', [])
    initial   = 10_000_000
    has_error = 'error' in bal

    win_trades   = trade_df[trade_df['pnl'] > 0] if not trade_df.empty and 'pnl' in trade_df.columns else pd.DataFrame()
    total_trades = len(trade_df)
    win_rate     = len(win_trades) / total_trades * 100 if total_trades > 0 else 0
    pnl_pct      = (total - initial) / initial * 100 if initial > 0 else 0

    today_signals = 0
    if not sig_df.empty and 'date' in sig_df.columns:
        try:
            today_signals = len(sig_df[sig_df['date'].dt.date == datetime.today().date()])
        except Exception:
            pass

    # ── 헤더 ────────────────────────────────────────────────────
    st.markdown("### Overview — Mission Control")
    if has_error:
        st.warning(f"KIS 연결 오류: {bal['error']} — 모의투자 API 토큰을 확인하세요.")

    # ── Row 1: KPI (st.metric 네이티브) ───────────────────────
    c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
    c1.metric("총 평가 (원)",   f"{total:,.0f}",       f"{pnl_pct:+.2f}%")
    c2.metric("평가 손익",      f"{pnl:+,.0f}원")
    c3.metric("예수금",         f"{cash:,.0f}원")
    c4.metric("오픈 포지션",    f"{len(positions)}개")
    c5.metric("총 체결",        f"{total_trades}건")
    c6.metric("승률",           f"{win_rate:.1f}%",    "▲ 양호" if win_rate >= 55 else "▼ 개선필요")
    c7.metric("오늘 신호",      f"{today_signals}건")
    c8.metric("총 누적 신호",   f"{len(sig_df)}건")

    st.divider()

    # ── Row 2: 자본곡선 + 오픈 포지션 ─────────────────────────
    left, right = st.columns([3, 2])

    with left:
        st.caption("자본 수익 곡선")
        if not trade_df.empty and 'pnl' in trade_df.columns and 'date' in trade_df.columns:
            df_s = trade_df.dropna(subset=['date']).sort_values('date')
            df_s = df_s.assign(cumulative=initial + df_s['pnl'].cumsum())

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_s['date'], y=df_s['cumulative'],
                mode='lines', line=dict(color='#26a69a', width=1.5),
                fill='tozeroy', fillcolor='rgba(38,166,154,0.08)',
                hovertemplate='%{x|%m/%d}<br>%{y:,.0f}원<extra></extra>',
            ))
            fig.add_hline(y=initial, line=dict(color='#363a45', dash='dash', width=1))
            fig.update_layout(
                height=200, margin=dict(t=4, b=4, l=4, r=4),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(size=11), showlegend=False,
                xaxis=dict(gridcolor='#2a2e39', zeroline=False, tickfont=dict(size=10)),
                yaxis=dict(gridcolor='#2a2e39', zeroline=False, tickfont=dict(size=10), tickformat=',.0f'),
            )
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        else:
            st.info("체결 내역 없음 — 자동매매 후 자동 표시")

    with right:
        st.caption("오픈 포지션")
        if positions:
            st.dataframe(pd.DataFrame(positions), width='stretch', hide_index=True, height=200)
        else:
            st.info("보유 포지션 없음")

    # ── Row 3: 손익분포 + 최근신호 + 최근체결 ──────────────────
    c_pie, c_sig, c_trd = st.columns([1, 2, 2])

    with c_pie:
        st.caption("승/패 비율")
        if total_trades > 0:
            lose_cnt = total_trades - len(win_trades)
            fig2 = go.Figure(go.Pie(
                values=[len(win_trades), lose_cnt],
                labels=['승', '패'], hole=0.65,
                marker_colors=['#26a69a', '#ef5350'],
                textfont=dict(size=10),
            ))
            fig2.update_layout(
                height=160, margin=dict(t=4, b=4, l=4, r=4),
                paper_bgcolor='rgba(0,0,0,0)', font=dict(size=11),
                showlegend=False,
                annotations=[dict(text=f"{win_rate:.0f}%", x=0.5, y=0.5,
                                  font=dict(size=15), showarrow=False)],
            )
            st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
        else:
            st.info("데이터 없음")

    with c_sig:
        st.caption("최근 신호 (8건)")
        if not sig_df.empty:
            show = [c for c in ['date','ticker','name','market','type','price','tp_pct','sl_pct'] if c in sig_df.columns]
            st.dataframe(sig_df[show].iloc[::-1].head(8).reset_index(drop=True),
                         width='stretch', hide_index=True, height=160)
        else:
            st.info("신호 없음")

    with c_trd:
        st.caption("최근 체결 (8건)")
        if not trade_df.empty:
            show = [c for c in ['date','ticker','action','qty','price','pnl','pnl_pct'] if c in trade_df.columns]
            st.dataframe(trade_df[show].iloc[::-1].head(8).reset_index(drop=True),
                         width='stretch', hide_index=True, height=160)
        else:
            st.info("체결 없음")

    # ── Row 4: 시장별 통계 ─────────────────────────────────────
    st.divider()
    st.caption("시장별 신호 통계")
    m1, m2, m3, m4, m5 = st.columns(5)

    def _mkt_cnt(mkt): return len(sig_df[sig_df['market'] == mkt]) if not sig_df.empty and 'market' in sig_df.columns else 0
    def _type_cnt(t):  return len(sig_df[sig_df['type'] == t])    if not sig_df.empty and 'type'   in sig_df.columns else 0

    m1.metric("한국주식 KR",   f"{_mkt_cnt('KR')}건")
    m2.metric("미국주식 US",   f"{_mkt_cnt('US')}건")
    m3.metric("암호화폐",      f"{_mkt_cnt('CRYPTO')}건")
    m4.metric("FVG 신호",      f"{_type_cnt('FVG')}건")
    m5.metric("OB 신호",       f"{_type_cnt('OB')}건")

    st.caption(f"업데이트: {datetime.now().strftime('%H:%M:%S')} — 30초 캐시")
