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
    st.markdown("### Backtest Results — 14종목 × 25전략 × 4타임프레임 | FVG+OB★ 필터링 비교")

    df_all  = _load('all_results.csv')
    df_rank = _load('strategy_ranking.csv')
    df_top3 = _load('top3_per_asset.csv')

    if df_all.empty:
        _empty_msg()
        return

    # ── 상단 KPI ─────────────────────────────────────────────────
    total_sims  = len(df_all)
    best_row    = df_all.loc[df_all['TotalRet%'].idxmax()] if len(df_all) > 0 else None
    fvg_df      = df_all[df_all['Strategy'] == 'FVG+OB']
    fvg_f_df    = df_all[df_all['Strategy'] == 'FVG+OB★']
    fvg_avg_wr  = fvg_df['WinRate%'].mean() if not fvg_df.empty else 0
    fvg_avg_pnl = fvg_df['TotalRet%'].mean() if not fvg_df.empty else 0
    fvgf_avg_wr = fvg_f_df['WinRate%'].mean() if not fvg_f_df.empty else 0
    fvgf_sharpe = fvg_f_df['Sharpe'].mean() if not fvg_f_df.empty else 0

    # 코인 4H 필터★ 평균
    coin4h_f = fvg_f_df[(fvg_f_df['Market'] == 'CRYPTO') & (fvg_f_df['Timeframe'] == '4h')]
    coin4h_pnl = coin4h_f['TotalRet%'].mean() if not coin4h_f.empty else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("총 시뮬레이션", f"{total_sims:,}건")
    k2.metric("FVG+OB 원본 WR", f"{fvg_avg_wr:.1f}%")
    k3.metric("FVG+OB★ 필터 WR", f"{fvgf_avg_wr:.1f}%",
              f"+{fvgf_avg_wr - fvg_avg_wr:.1f}%p")
    k4.metric("FVG+OB★ Sharpe", f"{fvgf_sharpe:.2f}")
    k5.metric("코인 4H★ 평균수익", f"{coin4h_pnl:+.1f}%")
    if best_row is not None:
        k6.metric("전체 최고", f"{best_row['TotalRet%']:+.1f}%",
                  f"{best_row['Ticker']} {best_row.get('Timeframe','')}")

    st.markdown("---")

    # ── 탭 구성 ──────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "FVG+OB 핵심 결과",
        "★ 필터 효과 비교",
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
        st.markdown("#### FVG+OB★ 필터링 효과 — 원본 vs 품질4점↑ + 하루5건 + 고유동성시간")

        fvg_orig = df_all[df_all['Strategy'] == 'FVG+OB'].copy()
        fvg_filt = df_all[df_all['Strategy'] == 'FVG+OB★'].copy()

        if fvg_orig.empty or fvg_filt.empty:
            st.info("FVG+OB★ 데이터 없음 — 백테스트를 재실행하세요")
        else:
            # 타임프레임별 WR / PnL / Sharpe 비교
            tfs = ['15m', '5m', '4h']
            orig_wr  = [fvg_orig[fvg_orig['Timeframe']==t]['WinRate%'].mean() for t in tfs]
            filt_wr  = [fvg_filt[fvg_filt['Timeframe']==t]['WinRate%'].mean() for t in tfs]
            orig_pnl = [fvg_orig[fvg_orig['Timeframe']==t]['TotalRet%'].mean() for t in tfs]
            filt_pnl = [fvg_filt[fvg_filt['Timeframe']==t]['TotalRet%'].mean() for t in tfs]
            orig_sh  = [fvg_orig[fvg_orig['Timeframe']==t]['Sharpe'].mean() for t in tfs]
            filt_sh  = [fvg_filt[fvg_filt['Timeframe']==t]['Sharpe'].mean() for t in tfs]

            c1, c2, c3 = st.columns(3)

            with c1:
                fig_wr = go.Figure()
                fig_wr.add_trace(go.Bar(name='원본', x=tfs, y=orig_wr,
                                        marker_color='#58a6ff', opacity=0.7))
                fig_wr.add_trace(go.Bar(name='★필터', x=tfs, y=filt_wr,
                                        marker_color='#26a69a'))
                fig_wr.update_layout(
                    title=dict(text='승률(%) 비교', font=dict(color='#d1d4dc', size=12)),
                    height=280, barmode='group',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=10),
                    margin=dict(t=35, b=10, l=40, r=10),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#8b949e', size=9)),
                    xaxis=dict(color='#8b949e'),
                    yaxis=dict(gridcolor='#2a2e39', color='#8b949e'),
                )
                st.plotly_chart(fig_wr, use_container_width=True, config={'displayModeBar': False})

            with c2:
                fig_pnl = go.Figure()
                fig_pnl.add_trace(go.Bar(name='원본', x=tfs, y=orig_pnl,
                                         marker_color='#58a6ff', opacity=0.7))
                fig_pnl.add_trace(go.Bar(name='★필터', x=tfs, y=filt_pnl,
                                         marker_color='#26a69a'))
                fig_pnl.update_layout(
                    title=dict(text='총수익(%) 비교', font=dict(color='#d1d4dc', size=12)),
                    height=280, barmode='group',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=10),
                    margin=dict(t=35, b=10, l=40, r=10),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#8b949e', size=9)),
                    xaxis=dict(color='#8b949e'),
                    yaxis=dict(gridcolor='#2a2e39', color='#8b949e'),
                )
                st.plotly_chart(fig_pnl, use_container_width=True, config={'displayModeBar': False})

            with c3:
                fig_sh = go.Figure()
                fig_sh.add_trace(go.Bar(name='원본', x=tfs, y=orig_sh,
                                        marker_color='#58a6ff', opacity=0.7))
                fig_sh.add_trace(go.Bar(name='★필터', x=tfs, y=filt_sh,
                                        marker_color='#e3b341'))
                fig_sh.update_layout(
                    title=dict(text='Sharpe 비교 (리스크 조정)', font=dict(color='#d1d4dc', size=12)),
                    height=280, barmode='group',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                    font=dict(color='#787b86', size=10),
                    margin=dict(t=35, b=10, l=40, r=10),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#8b949e', size=9)),
                    xaxis=dict(color='#8b949e'),
                    yaxis=dict(gridcolor='#2a2e39', color='#8b949e'),
                )
                st.plotly_chart(fig_sh, use_container_width=True, config={'displayModeBar': False})

            # 코인 4종 전용 섹션
            st.markdown("---")
            st.markdown("##### 코인 4종 (ETH/SOL/XRP/BTC) — FVG+OB★ 필터링 결과")
            coin_f = fvg_filt[fvg_filt['Market'] == 'CRYPTO']
            if not coin_f.empty:
                cc1, cc2, cc3, cc4 = st.columns(4)
                for col, tf in zip([cc1, cc2, cc3, cc4], ['4h', '15m', '5m', '1m+4h']):
                    sub = coin_f[coin_f['Timeframe'] == tf]
                    if not sub.empty:
                        col.metric(f"{tf} 평균수익",
                                   f"{sub['TotalRet%'].mean():+.1f}%",
                                   f"WR {sub['WinRate%'].mean():.0f}%  Sharpe {sub['Sharpe'].mean():.2f}")
                    else:
                        col.metric(f"{tf}", "데이터없음")

                # 종목별 4H 성과 바차트
                coin_4h = coin_f[coin_f['Timeframe'] == '4h'].sort_values('TotalRet%', ascending=True)
                if not coin_4h.empty:
                    fig_c = go.Figure(go.Bar(
                        y=coin_4h['Name'] if 'Name' in coin_4h.columns else coin_4h['Ticker'],
                        x=coin_4h['TotalRet%'],
                        orientation='h',
                        marker_color='#e3b341',
                        text=[f"WR:{wr:.0f}%  Q:{q:.0f}  Sharpe:{sh:.2f}"
                              for wr, q, sh in zip(coin_4h['WinRate%'],
                                                   coin_4h.get('quality_score', [0]*len(coin_4h)),
                                                   coin_4h['Sharpe'])],
                        textposition='outside',
                        textfont=dict(size=10),
                    ))
                    fig_c.update_layout(
                        title=dict(text='코인 4종 4H FVG+OB★ 총수익(%)', font=dict(color='#d1d4dc', size=13)),
                        height=260,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#1e222d',
                        font=dict(color='#787b86', size=11),
                        margin=dict(t=35, b=10, l=80, r=100),
                        xaxis=dict(gridcolor='#2a2e39', color='#8b949e', zeroline=True,
                                   zerolinecolor='#363a45'),
                        yaxis=dict(color='#8b949e'),
                    )
                    st.plotly_chart(fig_c, use_container_width=True, config={'displayModeBar': False})

            # 비교 요약 테이블
            st.markdown("##### 필터링 효과 요약")
            summary_rows = []
            for tf in ['4h', '15m', '5m']:
                o = fvg_orig[fvg_orig['Timeframe'] == tf]
                f = fvg_filt[fvg_filt['Timeframe'] == tf]
                if o.empty or f.empty:
                    continue
                summary_rows.append({
                    '타임프레임':   tf,
                    '원본_거래수':  int(o['Trades'].mean()),
                    '필터_거래수':  int(f['Trades'].mean()),
                    '거래감소%':   f"{(1 - f['Trades'].mean()/o['Trades'].mean())*100:.0f}%",
                    '원본_WR':     f"{o['WinRate%'].mean():.1f}%",
                    '필터_WR':     f"{f['WinRate%'].mean():.1f}%",
                    'WR_개선':     f"+{f['WinRate%'].mean()-o['WinRate%'].mean():.1f}%p",
                    '원본_Sharpe': f"{o['Sharpe'].mean():.2f}",
                    '필터_Sharpe': f"{f['Sharpe'].mean():.2f}",
                    'Sharpe_개선': f"+{f['Sharpe'].mean()-o['Sharpe'].mean():.2f}",
                })
            if summary_rows:
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════
    with tab3:  # 전략 랭킹
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
    with tab4:
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
    with tab5:
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
    with tab6:
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


    # ── V4.0 다전략 백테스트 결과 탭 ──────────────────────────
    with tab_v4:
        st.markdown('#### V4.0 다전략 백테스트 — 6전략 × KR98+US20+CRYPTO10 (2026-04-29)')
        st.info('BB반등(S5) 전략이 KR 78종목에서 평균 WR 64.1%, EV +1.958%로 압도적 1위')

        st.markdown('**전략별 성과 비교**')
        strategy_data = {
            '전략': ['S5_BBReversal', 'S6_Momentum', 'S2_SuperTrend', 'S4_GapGo', 'S3_MACD', 'S1_VWAP'],
            '채택종목수': [78, 57, 38, 41, 65, 60],
            '평균WR%': [64.1, 60.8, 62.9, 60.3, 57.1, 55.0],
            '평균EV%': [1.958, 2.204, 1.932, 1.405, 1.830, 1.345],
            '평균PF': [3.47, 3.10, 3.40, 3.63, 2.15, 2.15],
            '순위': [1, 2, 3, 4, 5, 6],
        }
        import pandas as pd
        st.dataframe(pd.DataFrame(strategy_data), use_container_width=True, hide_index=True)

        st.markdown('**V4.0 채택 종목 (시장별)**')
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('**KR — BB반등 1H**')
            kr_data = {
                '종목': ['SK텔레콤','코웨이','현대차','카카오','두산에너빌','하나금융','삼성중공업','한화시스템'],
                'WR%': [85.7,78.6,77.8,81.8,66.7,73.3,75.0,60.0],
                'EV%': [5.23,2.67,3.82,2.44,4.22,1.87,5.15,7.96],
            }
            st.dataframe(pd.DataFrame(kr_data), use_container_width=True, hide_index=True)
        with col2:
            st.markdown('**US — BB반등+Momentum 1H**')
            us_data = {
                '종목': ['AMD','마이크론','엔비디아','브로드컴','MSTR'],
                'WR%': [87.5,80.0,72.7,66.7,60.0],
                'EV%': [1.89,1.96,1.27,2.75,3.10],
            }
            st.dataframe(pd.DataFrame(us_data), use_container_width=True, hide_index=True)
        with col3:
            st.markdown('**CRYPTO — FVG+OB 4H (R:R 1:3)**')
            cr_data = {
                '종목': ['BTC','SOL','XRP','DOGE'],
                'WR%': [31.5,28.5,26.9,28.8],
                'EV%/trade': [0.187,0.209,0.137,0.193],
                '월수익%': [1.41,1.81,1.21,1.71],
            }
            st.dataframe(pd.DataFrame(cr_data), use_container_width=True, hide_index=True)

        st.markdown('**V5 통합 월수익 시뮬레이션 (시드 2,500만)**')
        sim_data = {
            '시장': ['KR (1,000만)', 'US (1,000만)', 'CRYPTO (500만)', '합계 (2,500만)'],
            '채택종목': ['대덕전자·삼성물산', 'AMD', 'BTC·SOL·XRP·DOGE', '-'],
            '월수익': ['+39만원', '+70만원', '+15만원', '+124만원'],
            '월수익률': ['3.91%', '6.96%', '2.74%', '4.95%'],
            'APY': ['46.9%', '83.5%', '32.9%', '59.4%'],
        }
        st.dataframe(pd.DataFrame(sim_data), use_container_width=True, hide_index=True)

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
