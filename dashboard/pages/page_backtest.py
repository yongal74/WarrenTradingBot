# -*- coding: utf-8 -*-
"""Backtest Results 페이지 — 백테스팅 결과 시각화"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

RESULT_DIR = Path(__file__).parent.parent.parent / 'backtest_results'

def render():
    st.markdown("## 📊 Backtest Results")
    st.markdown("2023-01-01 ~ 2025-12-31 일봉 기준, 25개 전략 × 15종목 백테스팅 결과")

    # ── 전략 종합 랭킹 ──────────────────────────────────────
    rank_path = RESULT_DIR / 'strategy_ranking.csv'
    if not rank_path.exists():
        st.warning("백테스팅 결과 파일이 없습니다. `trading_backtest/backtest_main.py`를 먼저 실행하세요.")
        return

    grp = pd.read_csv(rank_path, encoding='utf-8-sig')

    st.markdown("### 📈 전략별 평균 성과 (전 종목 기준)")

    # 신뢰도 필터 (all_results 기반)
    all_path = RESULT_DIR / 'all_results.csv'
    reliable_strategies = set()
    if all_path.exists():
        df_all = pd.read_csv(all_path, encoding='utf-8-sig')
        reliable = df_all[(df_all['Trades']>=5) & (df_all['ProfitFactor']<100)]
        reliable_strategies = set(reliable['Strategy'].unique())

    tab1, tab2, tab3 = st.tabs(["📊 수익률 랭킹", "📉 샤프/MDD", "🏆 종목별 TOP3"])

    with tab1:
        fig = go.Figure()
        top15 = grp.head(15).reset_index(drop=True)
        colors = ['#3fb950' if s in reliable_strategies else '#58a6ff'
                  for s in top15['Strategy']]
        fig.add_trace(go.Bar(
            x=top15['avg_ret']*100, y=top15['Strategy'],
            orientation='h', marker_color=colors,
            text=[f"{v:.1f}%" for v in top15['avg_ret']*100],
            textposition='outside',
        ))
        fig.update_layout(
            height=500, paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,17,23,0.8)', font_color='#e6edf3',
            xaxis=dict(title='평균 수익률 (%)',gridcolor='#21262d',color='#8b949e'),
            yaxis=dict(color='#8b949e'),
            margin=dict(t=10,b=30,l=180,r=80),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("🟢 신뢰가능(거래수≥5, PF<100) | 🔵 참고용")

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            top_sh = grp.sort_values('avg_sh',ascending=False).head(10).reset_index(drop=True)
            fig2 = go.Figure(go.Bar(
                x=top_sh['avg_sh'], y=top_sh['Strategy'], orientation='h',
                marker_color='#58a6ff',
                text=[f"{v:.2f}" for v in top_sh['avg_sh']], textposition='outside',
            ))
            fig2.update_layout(
                height=350, title='샤프 지수 TOP10',
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,17,23,0.8)',
                font_color='#e6edf3', margin=dict(t=40,b=20,l=180,r=60),
                xaxis=dict(gridcolor='#21262d',color='#8b949e'),
                yaxis=dict(color='#8b949e'),
            )
            st.plotly_chart(fig2, use_container_width=True)

        with col2:
            top_mdd = grp.sort_values('avg_mdd',ascending=False).head(10).reset_index(drop=True)
            fig3 = go.Figure(go.Bar(
                x=top_mdd['avg_mdd']*100, y=top_mdd['Strategy'], orientation='h',
                marker_color='#f85149',
                text=[f"{v:.1f}%" for v in top_mdd['avg_mdd']*100], textposition='outside',
            ))
            fig3.update_layout(
                height=350, title='MDD 낮은 전략 TOP10',
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,17,23,0.8)',
                font_color='#e6edf3', margin=dict(t=40,b=20,l=180,r=60),
                xaxis=dict(gridcolor='#21262d',color='#8b949e',title='MDD (%)'),
                yaxis=dict(color='#8b949e'),
            )
            st.plotly_chart(fig3, use_container_width=True)

    with tab3:
        top3_path = RESULT_DIR / 'top3_per_asset.csv'
        if top3_path.exists():
            df3 = pd.read_csv(top3_path, encoding='utf-8-sig')
            st.dataframe(df3, use_container_width=True, hide_index=True)
        else:
            st.info("top3_per_asset.csv 없음")

    # ── 종목별 상세 ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔍 종목별 전략 성과 상세")

    if all_path.exists():
        df_all = pd.read_csv(all_path, encoding='utf-8-sig')
        ticker_sel = st.selectbox("종목 선택", df_all['Ticker'].unique())
        df_sel = df_all[df_all['Ticker']==ticker_sel].sort_values('_tr',ascending=False)
        df_sel_show = df_sel[['Strategy','TotalRet%','WinRate%','ProfitFactor','MDD%','Sharpe','Trades']].copy()

        def color_ret(val):
            if isinstance(val, (int,float)):
                return 'color: #3fb950' if val > 0 else 'color: #f85149'
            return ''

        st.dataframe(
            df_sel_show.style.map(color_ret, subset=['TotalRet%','MDD%']),
            use_container_width=True, hide_index=True
        )
