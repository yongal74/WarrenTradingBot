# -*- coding: utf-8 -*-
"""Backtest Results — 14종목 × 25전략 × 4타임프레임 시각화"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

RESULT_DIR = Path(__file__).parent.parent.parent / 'backtest_results'

_TF_COLOR = {'15m': '#2962ff', '5m': '#26a69a', '4h': '#e3b341', '1m+4h': '#ff7b72'}
_MKT_COLOR = {'KR': '#26a69a', 'US': '#2962ff', 'CRYPTO': '#e3b341'}


@st.cache_data(ttl=60)
def _load(name: str) -> pd.DataFrame:
    p = RESULT_DIR / name
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p, encoding='utf-8-sig')
    except Exception:
        return pd.DataFrame()


def _empty_msg():
    st.info("백테스트 결과 없음")
    if st.button("백테스트 즉시 실행"):
        import subprocess, sys
        subprocess.Popen(
            [sys.executable, 'run_backtest_all.py'],
            cwd=str(Path(__file__).parent.parent.parent)
        )
        st.success("백테스트 시작됨 — 약 3~5분 소요. 완료 후 새로고침하세요.")


def render():
    st.markdown("### Backtest Results — 14종목 × 25전략 × 4타임프레임")

    df_all  = _load('all_results.csv')
    df_rank = _load('strategy_ranking.csv')
    df_top3 = _load('top3_per_asset.csv')

    if df_all.empty:
        _empty_msg()
        return

    # ── 상단 KPI ─────────────────────────────────────────────────
    total_sims = len(df_all)
    best_row   = df_all.loc[df_all['TotalRet%'].idxmax()] if len(df_all) > 0 else None
    fvg_df     = df_all[df_all['Strategy'] == 'FVG+OB']
    fvg_avg_wr = fvg_df['WinRate%'].mean() if not fvg_df.empty else 0
    fvg_avg_pnl= fvg_df['TotalRet%'].mean() if not fvg_df.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("총 시뮬레이션", f"{total_sims:,}건")
    k2.metric("FVG+OB 평균 승률", f"{fvg_avg_wr:.1f}%")
    k3.metric("FVG+OB 평균 수익", f"{fvg_avg_pnl:+.1f}%")
    if best_row is not None:
        k4.metric("최고 전략",
                  f"{best_row['Strategy']} / {best_row.get('Timeframe','')}")
        k5.metric("최고 수익률",
                  f"{best_row['TotalRet%']:+.1f}%",
                  f"{best_row['Ticker']} {best_row.get('Market','')}")

    st.markdown("---")

    # ── 탭 구성 ──────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "FVG+OB 핵심 결과",
        "전략 랭킹",
        "타임프레임 비교",
        "종목별 TOP3",
        "전체 데이터",
    ])

    # ════════════════════════════════════════════════════════
    with tab1:
        st.markdown("#### FVG+OB 전략 — 14종목 × 4타임프레임")

        fvg = df_all[df_all['Strategy'] == 'FVG+OB'].copy()
        if fvg.empty:
            st.info("FVG+OB 결과 없음")
        else:
            # 타임프레임별 × 종목별 수익 히트맵
            tfs = [t for t in ['15m', '5m', '4h', '1m+4h'] if t in fvg['Timeframe'].values]
            pivot = fvg.pivot_table(index='Ticker', columns='Timeframe',
                                     values='TotalRet%', aggfunc='mean').reindex(columns=tfs)
            pivot = pivot.fillna(0)

            fig_heat = go.Figure(go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale=[[0,'#f85149'],[0.5,'#2a2e39'],[1,'#26a69a']],
                zmid=0,
                text=np.round(pivot.values, 1),
                texttemplate='%{text}%',
                textfont=dict(size=11),
                colorbar=dict(title='총수익%', tickfont=dict(color='#787b86')),
            ))
            fig_heat.update_layout(
                title=dict(text='종목 × 타임프레임 FVG+OB 총수익(%)', font=dict(color='#d1d4dc', size=13)),
                height=380,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                font=dict(color='#787b86', size=11),
                margin=dict(t=40, b=10, l=80, r=10),
                xaxis=dict(color='#8b949e'), yaxis=dict(color='#8b949e'),
            )
            st.plotly_chart(fig_heat, use_container_width=True, config={'displayModeBar': False})

            # 종목별 성과 바차트 (15m 기준)
            fvg15 = fvg[fvg['Timeframe'] == '15m'].sort_values('TotalRet%', ascending=True)
            if not fvg15.empty:
                colors = [_MKT_COLOR.get(m, '#58a6ff') for m in fvg15['Market']]
                fig_bar = go.Figure(go.Bar(
                    y=fvg15['Ticker'],
                    x=fvg15['TotalRet%'],
                    orientation='h',
                    marker_color=colors,
                    text=[f"WR:{wr:.0f}% N:{n:.0f}" for wr, n
                          in zip(fvg15['WinRate%'], fvg15['Trades'])],
                    textposition='outside',
                    textfont=dict(size=10),
                ))
                fig_bar.update_layout(
                    title=dict(text='FVG+OB 15분봉 — 종목별 총수익(%)', font=dict(color='#d1d4dc', size=13)),
                    height=380,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=11),
                    margin=dict(t=40, b=10, l=80, r=80),
                    xaxis=dict(gridcolor='#2a2e39', color='#8b949e', zeroline=True,
                               zerolinecolor='#363a45'),
                    yaxis=dict(color='#8b949e'),
                )
                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

            # 상세 테이블
            show = ['Ticker', 'Name', 'Market', 'Timeframe', 'Trades',
                    'WinRate%', 'TotalRet%', 'ProfitFactor', 'Sharpe', 'MDD%']
            show = [c for c in show if c in fvg.columns]
            st.dataframe(fvg[show].sort_values(['Timeframe','TotalRet%'], ascending=[True,False]),
                         use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════
    with tab2:
        st.markdown("#### 전략 랭킹 — 평균 총수익 기준")

        if df_rank.empty:
            st.info("ranking 데이터 없음")
        else:
            # 타임프레임 필터
            tfs_avail = sorted(df_rank['Timeframe'].unique()) if 'Timeframe' in df_rank.columns else ['15m']
            sel_tf = st.selectbox("타임프레임", tfs_avail, key='rank_tf')

            ranked = df_rank[df_rank['Timeframe'] == sel_tf].sort_values('avg_ret', ascending=False).head(20)

            if not ranked.empty:
                colors = ['#26a69a' if v > 0 else '#ef5350' for v in ranked['avg_ret']]
                fig_rank = go.Figure()
                fig_rank.add_trace(go.Bar(
                    y=ranked['Strategy'],
                    x=ranked['avg_ret'],
                    orientation='h',
                    marker_color=colors,
                    text=[f"{v:+.2f}% WR:{wr:.0f}%"
                          for v, wr in zip(ranked['avg_ret'], ranked.get('avg_wr', [0]*len(ranked)))],
                    textposition='outside',
                    textfont=dict(size=10),
                ))
                fig_rank.update_layout(
                    title=dict(text=f'전략 평균 수익률 TOP20 [{sel_tf}]', font=dict(color='#d1d4dc', size=13)),
                    height=500,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=11),
                    margin=dict(t=40, b=10, l=160, r=100),
                    xaxis=dict(gridcolor='#2a2e39', color='#8b949e', zeroline=True,
                               zerolinecolor='#363a45'),
                    yaxis=dict(color='#8b949e'),
                )
                st.plotly_chart(fig_rank, use_container_width=True, config={'displayModeBar': False})

                # Sharpe vs Return 산점도
                fig_sc = go.Figure()
                for _, row in df_rank[df_rank['Timeframe'] == sel_tf].iterrows():
                    color = _TF_COLOR.get(sel_tf, '#58a6ff')
                    fig_sc.add_trace(go.Scatter(
                        x=[row['avg_ret']], y=[row.get('avg_sh', 0)],
                        mode='markers+text',
                        text=[row['Strategy']],
                        textposition='top center',
                        textfont=dict(size=9, color='#787b86'),
                        marker=dict(size=8, color=color, opacity=0.8),
                        showlegend=False,
                    ))
                fig_sc.update_layout(
                    title=dict(text='수익률 vs 샤프 지수', font=dict(color='#d1d4dc', size=13)),
                    height=380,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=11),
                    margin=dict(t=40, b=40, l=50, r=10),
                    xaxis=dict(gridcolor='#2a2e39', color='#8b949e', title='평균 총수익(%)'),
                    yaxis=dict(gridcolor='#2a2e39', color='#8b949e', title='평균 샤프'),
                )
                fig_sc.add_vline(x=0, line=dict(color='#363a45', dash='dash'))
                fig_sc.add_hline(y=0, line=dict(color='#363a45', dash='dash'))
                st.plotly_chart(fig_sc, use_container_width=True, config={'displayModeBar': False})

    # ════════════════════════════════════════════════════════
    with tab3:
        st.markdown("#### 타임프레임 비교 — FVG+OB")

        fvg2 = df_all[df_all['Strategy'] == 'FVG+OB'].copy()
        if fvg2.empty:
            st.info("데이터 없음")
        else:
            # 타임프레임별 박스플롯
            fig_box = go.Figure()
            for tf, color in _TF_COLOR.items():
                sub = fvg2[fvg2['Timeframe'] == tf]
                if sub.empty: continue
                fig_box.add_trace(go.Box(
                    y=sub['TotalRet%'], name=tf,
                    marker_color=color, line_color=color,
                    boxmean=True,
                ))
            fig_box.update_layout(
                title=dict(text='타임프레임별 FVG+OB 총수익 분포', font=dict(color='#d1d4dc', size=13)),
                height=350,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                font=dict(color='#787b86', size=11),
                margin=dict(t=40, b=10, l=50, r=10),
                xaxis=dict(color='#8b949e'),
                yaxis=dict(gridcolor='#2a2e39', color='#8b949e', title='총수익(%)'),
                showlegend=True,
                legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#8b949e')),
            )
            fig_box.add_hline(y=0, line=dict(color='#363a45', dash='dash'))
            st.plotly_chart(fig_box, use_container_width=True, config={'displayModeBar': False})

            # 타임프레임별 평균 지표 테이블
            tf_summary = fvg2.groupby('Timeframe').agg(
                종목수=('Ticker','count'),
                평균거래수=('Trades','mean'),
                평균승률=('WinRate%','mean'),
                평균수익=('TotalRet%','mean'),
                평균PF=('ProfitFactor','mean'),
                평균샤프=('Sharpe','mean'),
                평균MDD=('MDD%','mean'),
            ).round(2).reset_index()
            st.dataframe(tf_summary, use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════
    with tab4:
        st.markdown("#### 종목별 TOP3 전략")

        if df_top3.empty:
            st.info("top3 데이터 없음")
        else:
            ticker_list = sorted(df_top3['Ticker'].unique())
            sel_ticker  = st.selectbox("종목 선택", ['전체'] + ticker_list, key='top3_tk')

            df_show = df_top3 if sel_ticker == '전체' else df_top3[df_top3['Ticker'] == sel_ticker]

            if not df_show.empty:
                # 종목별 최고 전략 바차트
                best_per = df_show.sort_values('TotalRet%', ascending=False).drop_duplicates('Ticker')
                fig_top = go.Figure()
                for mkt, color in _MKT_COLOR.items():
                    sub = best_per[best_per['Market'] == mkt]
                    if sub.empty: continue
                    fig_top.add_trace(go.Bar(
                        x=sub['Ticker'], y=sub['TotalRet%'],
                        name=mkt, marker_color=color,
                        text=[f"{s}<br>{tf}" for s, tf in zip(sub['Strategy'], sub.get('Timeframe', [''] * len(sub)))],
                        textposition='outside', textfont=dict(size=9),
                    ))
                fig_top.update_layout(
                    title=dict(text='종목별 최고 전략 수익률', font=dict(color='#d1d4dc', size=13)),
                    height=380, barmode='group',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=11),
                    margin=dict(t=40, b=60, l=50, r=10),
                    xaxis=dict(color='#8b949e'),
                    yaxis=dict(gridcolor='#2a2e39', color='#8b949e', title='총수익(%)'),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#8b949e')),
                )
                fig_top.add_hline(y=0, line=dict(color='#363a45', dash='dash'))
                st.plotly_chart(fig_top, use_container_width=True, config={'displayModeBar': False})

                cols = ['Ticker', 'Name', 'Market', 'Strategy', 'Timeframe',
                        'WinRate%', 'TotalRet%', 'ProfitFactor', 'Sharpe', 'Trades']
                cols = [c for c in cols if c in df_show.columns]
                st.dataframe(df_show[cols].sort_values('TotalRet%', ascending=False),
                             use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════
    with tab5:
        st.markdown("#### 전체 결과 데이터")

        col1, col2, col3 = st.columns(3)
        with col1:
            tf_f = st.multiselect("타임프레임", sorted(df_all['Timeframe'].unique()),
                                   default=sorted(df_all['Timeframe'].unique()), key='all_tf')
        with col2:
            mkt_f = st.multiselect("시장", sorted(df_all['Market'].unique()),
                                    default=sorted(df_all['Market'].unique()), key='all_mkt')
        with col3:
            strat_f = st.multiselect("전략", sorted(df_all['Strategy'].unique()),
                                      default=['FVG+OB'], key='all_strat')

        filtered = df_all[
            df_all['Timeframe'].isin(tf_f) &
            df_all['Market'].isin(mkt_f) &
            df_all['Strategy'].isin(strat_f)
        ]

        st.caption(f"{len(filtered):,}건")

        show_cols = ['Ticker', 'Name', 'Market', 'Timeframe', 'Strategy',
                     'Trades', 'WinRate%', 'TotalRet%', 'ProfitFactor', 'Sharpe', 'MDD%']
        show_cols = [c for c in show_cols if c in filtered.columns]
        st.dataframe(
            filtered[show_cols].sort_values('TotalRet%', ascending=False),
            use_container_width=True, hide_index=True, height=500
        )

        if not filtered.empty:
            csv = filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("CSV 다운로드", csv, "backtest_filtered.csv", "text/csv")

    # ── 재실행 버튼 ─────────────────────────────────────────────
    st.markdown("---")
    col_run, col_info = st.columns([1, 3])
    with col_run:
        if st.button("백테스트 재실행", type="primary"):
            import subprocess
            subprocess.Popen(
                [sys.executable, 'run_backtest_all.py'],
                cwd=str(Path(__file__).parent.parent.parent)
            )
            st.success("백그라운드 실행 시작 — 약 3~5분 소요")
    with col_info:
        st.caption("14종목 × 25전략 × 4타임프레임 (1m+4h / 5m / 15m / 4h) | yfinance 실데이터")
