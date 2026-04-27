# -*- coding: utf-8 -*-
"""Trade Log — 체결 내역 · 수익분석 · 백테스트 비교"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'
BT_DIR  = Path(__file__).parent.parent.parent / 'backtest_results'


def _load_trades() -> pd.DataFrame:
    p = LOG_DIR / 'trade_log.csv'
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, encoding='utf-8-sig')
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


def _load_kis() -> pd.DataFrame:
    p = LOG_DIR / 'kis_trades.csv'
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, encoding='utf-8-sig')
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


def _performance_stats(df: pd.DataFrame, initial: float = 10_000_000) -> dict:
    if df.empty or 'pnl' not in df.columns:
        return {}
    total_trades = len(df)
    wins  = df[df['pnl'] > 0]
    loses = df[df['pnl'] <= 0]
    total_pnl = df['pnl'].sum()
    win_rate  = len(wins) / total_trades * 100 if total_trades > 0 else 0
    avg_win   = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss  = loses['pnl'].mean() if len(loses) > 0 else 0
    profit_factor = abs(wins['pnl'].sum() / loses['pnl'].sum()) if loses['pnl'].sum() != 0 else 999.0

    cum  = initial + df.sort_values('date')['pnl'].cumsum() if 'date' in df.columns else pd.Series([initial])
    peak = cum.cummax()
    dd   = (cum - peak) / peak * 100
    max_dd = dd.min()

    return {
        'total_trades': total_trades,
        'win_rate':     round(win_rate, 1),
        'total_pnl':    round(total_pnl, 0),
        'avg_win':      round(avg_win, 0),
        'avg_loss':     round(avg_loss, 0),
        'profit_factor':round(profit_factor, 2),
        'max_dd':       round(max_dd, 2),
    }


def render():
    st.markdown("### Trade Log — 체결 내역 & 수익 분석")

    tab1, tab2, tab3, tab4 = st.tabs([
        "포워드 체결 로그", "KIS 모의투자 체결", "수익 분석", "백테스트 결과"
    ])

    def _kpi(col, label, val, color='#d1d4dc'):
        col.markdown(f"""<div class='kpi-card'>
        <div class='kpi-val' style='color:{color};font-size:16px;'>{val}</div>
        <div class='kpi-label'>{label}</div></div>""", unsafe_allow_html=True)

    # ── Tab1: 포워드 체결 ───────────────────────────────────────
    with tab1:
        df = _load_trades()
        if not df.empty:
            stats = _performance_stats(df)
            c1,c2,c3,c4,c5,c6 = st.columns(6)
            _kpi(c1, "총 체결", f"{stats.get('total_trades',0)}건")
            _kpi(c2, "승률", f"{stats.get('win_rate',0):.1f}%",
                 '#26a69a' if stats.get('win_rate',0) >= 55 else '#787b86')
            _kpi(c3, "총 손익", f"{stats.get('total_pnl',0):+,.0f}원",
                 '#26a69a' if stats.get('total_pnl',0) >= 0 else '#ef5350')
            _kpi(c4, "평균 수익", f"{stats.get('avg_win',0):+,.0f}원", '#26a69a')
            _kpi(c5, "평균 손실", f"{stats.get('avg_loss',0):+,.0f}원", '#ef5350')
            _kpi(c6, "MDD", f"{stats.get('max_dd',0):.2f}%", '#ef5350')

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            show_cols = [c for c in ['date','ticker','name','action','qty','price',
                                     'amount','pnl','pnl_pct','strategy'] if c in df.columns]
            st.dataframe(df[show_cols].iloc[::-1].reset_index(drop=True),
                         width='stretch', hide_index=True, height=400)
            st.download_button("CSV 다운로드",
                               df.to_csv(index=False).encode('utf-8-sig'),
                               "trade_log.csv", "text/csv")
        else:
            st.info("체결 내역 없음 — 자동매매 실행 후 표시됩니다")

    # ── Tab2: KIS 체결 ──────────────────────────────────────────
    with tab2:
        kis_df = _load_kis()
        if not kis_df.empty:
            stats2 = _performance_stats(kis_df)
            c1,c2,c3,c4 = st.columns(4)
            _kpi(c1, "총 체결", f"{stats2.get('total_trades',0)}건")
            _kpi(c2, "승률", f"{stats2.get('win_rate',0):.1f}%")
            _kpi(c3, "총 손익", f"{stats2.get('total_pnl',0):+,.0f}원",
                 '#26a69a' if stats2.get('total_pnl',0) >= 0 else '#ef5350')
            _kpi(c4, "Profit Factor", f"{stats2.get('profit_factor',0):.2f}")
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.dataframe(kis_df.iloc[::-1].reset_index(drop=True),
                         width='stretch', hide_index=True, height=400)
        else:
            st.info("KIS 체결 내역 없음 — run_kr_autotrader.py 실행 후 표시")

    # ── Tab3: 수익 분석 차트 ────────────────────────────────────
    with tab3:
        df = _load_trades()
        if not df.empty and 'pnl' in df.columns and 'date' in df.columns:
            df_s = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
            df_s['cumulative'] = 10_000_000 + df_s['pnl'].cumsum()
            df_s['dd'] = (df_s['cumulative'] - df_s['cumulative'].cummax()) / df_s['cumulative'].cummax() * 100

            fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                row_heights=[0.5, 0.25, 0.25],
                                vertical_spacing=0.02)

            fig.add_trace(go.Scatter(
                x=df_s['date'], y=df_s['cumulative'],
                line=dict(color='#26a69a', width=1.5),
                fill='tozeroy', fillcolor='rgba(38,166,154,0.06)',
                name='자본', hovertemplate='%{y:,.0f}원<extra></extra>',
            ), row=1, col=1)
            fig.add_hline(y=10_000_000, line=dict(color='#363a45', dash='dash', width=1), row=1, col=1)

            bar_colors = ['#26a69a' if p > 0 else '#ef5350' for p in df_s['pnl']]
            fig.add_trace(go.Bar(x=df_s['date'], y=df_s['pnl'],
                                 marker_color=bar_colors, name='개별 손익',
                                 hovertemplate='%{y:+,.0f}원<extra></extra>'), row=2, col=1)

            fig.add_trace(go.Scatter(
                x=df_s['date'], y=df_s['dd'],
                line=dict(color='#ef5350', width=1),
                fill='tozeroy', fillcolor='rgba(239,83,80,0.08)',
                name='DD', hovertemplate='%{y:.2f}%<extra></extra>',
            ), row=3, col=1)

            _ax = dict(gridcolor='#1e222d', zeroline=False, color='#787b86', tickfont=dict(size=10))
            fig.update_layout(
                height=520, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#131722',
                font=dict(color='#787b86', size=11),
                margin=dict(t=8, b=4, l=4, r=4),
                showlegend=False, hovermode='x unified',
            )
            for r in [1,2,3]:
                fig.update_xaxes(**_ax, row=r, col=1)
                fig.update_yaxes(**_ax, row=r, col=1)
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

            if 'strategy' in df.columns:
                st.markdown("<div class='sec-hdr'>전략별 성과</div>", unsafe_allow_html=True)
                grp = df.groupby('strategy').agg(
                    체결수=('pnl','count'),
                    총손익=('pnl','sum'),
                    평균손익=('pnl','mean'),
                    승건=('pnl', lambda x: (x > 0).sum()),
                ).reset_index()
                grp['승률'] = (grp['승건'] / grp['체결수'] * 100).round(1)
                st.dataframe(grp.sort_values('총손익', ascending=False),
                             width='stretch', hide_index=True)
        else:
            st.info("분석할 체결 데이터 없음")

    # ── Tab4: 백테스트 결과 ─────────────────────────────────────
    with tab4:
        bt_files = list(BT_DIR.glob('*.csv')) if BT_DIR.exists() else []

        if bt_files:
            sel = st.selectbox("결과 파일", [f.name for f in bt_files],
                               label_visibility='collapsed')
            try:
                bt_df = pd.read_csv(BT_DIR / sel, encoding='utf-8-sig')
                num_cols = bt_df.select_dtypes(include=[np.number]).columns.tolist()
                if num_cols:
                    st.dataframe(bt_df[num_cols].describe().round(2), width='stretch')
                st.dataframe(bt_df.head(200), width='stretch', hide_index=True, height=350)
                st.download_button("CSV 다운로드",
                                   bt_df.to_csv(index=False).encode('utf-8-sig'),
                                   sel, "text/csv")
            except Exception as e:
                st.error(f"파일 로드 오류: {e}")
        else:
            st.markdown("<div class='sec-hdr'>FVG+OB 백테스트 요약 (60일 15분봉)</div>",
                        unsafe_allow_html=True)
            summary = pd.DataFrame([
                {'시장':'한국주식 KR','대표종목':'삼성전자,SK하이닉스','시드':'1,000만원',
                 '월 수익':'+267만원','승률':'~56%','R:R':'1:2'},
                {'시장':'미국주식 US','대표종목':'NVDA,TSLA,AMD','시드':'1,000만원',
                 '월 수익':'+187만원','승률':'~52%','R:R':'1:2'},
                {'시장':'암호화폐','대표종목':'ETH,SOL,BNB','시드':'1,000만원',
                 '월 수익':'+203만원','승률':'~51%','R:R':'1:2'},
            ])
            st.dataframe(summary, width='stretch', hide_index=True)
            st.caption("* 과거 백테스트 결과이며 미래 수익을 보장하지 않습니다.")

            if st.button("백테스트 재실행 (3시장)", type="primary"):
                with st.spinner("백테스트 실행 중... (수 분 소요)"):
                    try:
                        import subprocess
                        result = subprocess.run(
                            ['python', 'trading_backtest/backtest_3market.py'],
                            capture_output=True, text=True, timeout=300,
                            cwd=str(Path(__file__).parent.parent.parent)
                        )
                        if result.returncode == 0:
                            st.success("백테스트 완료")
                            st.code(result.stdout[-2000:])
                        else:
                            st.error(result.stderr[-1000:])
                    except Exception as e:
                        st.error(f"실행 오류: {e}")
