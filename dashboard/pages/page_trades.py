# -*- coding: utf-8 -*-
"""Trade Log — KIS 체결 + 포워드 신호 통합 로그"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'

def render():
    st.markdown("## 거래 내역")

    tab1, tab2, tab3 = st.tabs(["KIS 체결", "FVG+OB 신호 로그", "백테스트 결과"])

    # ── Tab1: KIS 체결 내역 ────────────────────────────────────
    with tab1:
        st.markdown("### KIS 모의투자 체결 내역")
        path = LOG_DIR / 'kis_trades.csv'
        if not path.exists():
            st.info("아직 체결 내역이 없습니다. 자동매매 봇 실행 후 표시됩니다.")
        else:
            df = pd.read_csv(path, encoding='utf-8-sig')
            if df.empty:
                st.info("체결 내역 없음")
            else:
                buys  = df[df['side']=='BUY']
                sells = df[df['side']=='SELL']

                c1, c2, c3 = st.columns(3)
                with c1: st.metric("총 매수", f"{len(buys)}건")
                with c2: st.metric("총 매도", f"{len(sells)}건")
                with c3: st.metric("성공률", f"{df['success'].mean()*100:.0f}%")

                st.dataframe(df.iloc[::-1], use_container_width=True, hide_index=True)
                st.download_button("CSV 다운로드", df.to_csv(index=False).encode('utf-8-sig'),
                                   "kis_trades.csv", "text/csv")

    # ── Tab2: FVG+OB 신호 로그 ────────────────────────────────
    with tab2:
        st.markdown("### FVG+OB 포워드 신호 누적 로그")
        path2 = LOG_DIR / 'forward_signals.csv'
        if not path2.exists():
            st.info("신호 로그 없음. 포워드 테스터가 실행되면 여기에 기록됩니다.")
        else:
            df2 = pd.read_csv(path2, encoding='utf-8-sig')
            if df2.empty:
                st.info("신호 없음")
            else:
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("총 신호", f"{len(df2)}건")
                with c2: st.metric("KR 신호", f"{len(df2[df2['market']=='KR'])}건")
                with c3: st.metric("US 신호", f"{len(df2[df2['market']=='US'])}건")
                with c4:
                    fvg = len(df2[df2['type']=='FVG'])
                    ob  = len(df2[df2['type']=='OB'])
                    st.metric("FVG/OB", f"{fvg}/{ob}")

                # 신호 타입별 차트
                col_l, col_r = st.columns(2)
                with col_l:
                    if 'market' in df2.columns:
                        mkt = df2['market'].value_counts()
                        fig = go.Figure(go.Pie(
                            labels=mkt.index, values=mkt.values,
                            hole=0.5,
                            marker_colors=['#3fb950','#58a6ff','#e3b341'],
                        ))
                        fig.update_layout(
                            title='시장별 신호', height=250,
                            paper_bgcolor='rgba(0,0,0,0)',
                            font_color='#e6edf3', margin=dict(t=40,b=10,l=10,r=10),
                        )
                        st.plotly_chart(fig, use_container_width=True)
                with col_r:
                    if 'type' in df2.columns:
                        tp = df2['type'].value_counts()
                        fig2 = go.Figure(go.Pie(
                            labels=tp.index, values=tp.values,
                            hole=0.5,
                            marker_colors=['#238636','#1f6feb'],
                        ))
                        fig2.update_layout(
                            title='FVG vs OB', height=250,
                            paper_bgcolor='rgba(0,0,0,0)',
                            font_color='#e6edf3', margin=dict(t=40,b=10,l=10,r=10),
                        )
                        st.plotly_chart(fig2, use_container_width=True)

                st.dataframe(df2.iloc[::-1], use_container_width=True, hide_index=True)
                st.download_button("CSV 다운로드", df2.to_csv(index=False).encode('utf-8-sig'),
                                   "forward_signals.csv", "text/csv")

    # ── Tab3: 백테스트 결과 ────────────────────────────────────
    with tab3:
        st.markdown("### 백테스트 결과 (FVG+OB 15분봉)")
        br_dir = Path(__file__).parent.parent.parent / 'backtest_results'
        csvs = sorted(br_dir.glob('3market_compare_*.csv'), reverse=True) if br_dir.exists() else []

        if not csvs:
            st.info("백테스트 결과 없음 — backtest_3market.py 실행 필요")
        else:
            latest = csvs[0]
            df3 = pd.read_csv(latest, encoding='utf-8-sig')
            st.caption(f"파일: {latest.name}")

            for mkt in ['KR','US','CRYPTO']:
                mdf = df3[df3['market']==mkt]
                if mdf.empty: continue
                st.markdown(f"**{mkt} 시장**")

                display = mdf[['name','code','A_n','A_wr','A_ev','A_pnl','B_n','B_wr','B_ev','B_pnl','best']].copy()
                display.columns = ['종목','코드','A거래수','A승률%','A기대값%','A월수익',
                                   'B거래수','B승률%','B기대값%','B월수익','추천']
                st.dataframe(display, use_container_width=True, hide_index=True)

                # 월 수익 막대그래프
                fig = go.Figure()
                fig.add_trace(go.Bar(name='FVG+OB', x=mdf['name'], y=mdf['A_pnl'],
                                     marker_color='#3fb950'))
                fig.add_trace(go.Bar(name='FVG+OB+DBB', x=mdf['name'], y=mdf['B_pnl'],
                                     marker_color='#58a6ff'))
                fig.update_layout(
                    barmode='group', height=250,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(13,17,23,0.8)',
                    font_color='#e6edf3',
                    margin=dict(t=10,b=30,l=60,r=10),
                    yaxis_title='월 수익 (원)',
                    legend=dict(font_color='#e6edf3'),
                )
                st.plotly_chart(fig, use_container_width=True)
