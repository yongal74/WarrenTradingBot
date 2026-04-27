# -*- coding: utf-8 -*-
"""Strategy Factory — 25개 전략 + C1~C5 합류점 + FVG+OB 신호 현황"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config.assets import ALL_ASSETS, PRIMARY_STRATEGY
from core.strategy_factory import get_all_signals
from core.confluence_engine import get_latest_scores, MIN_SCORE
from data.data_loader import load

STRATEGY_DESC = {
    'S01_EMA9_21':    'EMA 9/21 크로스',
    'S02_EMA20_50':   'EMA 20/50 크로스',
    'S03_GoldenCross':'골든/데드크로스 50/200',
    'S04_SuperTrend': 'SuperTrend 추세',
    'S05_HullMA':     'Hull MA 크로스',
    'S06_Ichimoku':   '일목균형표 클라우드',
    'S07_RSI_Trend':  'RSI>50 추세',
    'S08_RSI_Rev':    'RSI 평균회귀',
    'S09_MACD':       'MACD 시그널 크로스',
    'S10_MACDHist':   'MACD 히스토그램',
    'S11_BB_Break':   'BB 상단 돌파',
    'S12_BB_Rev':     'BB 평균회귀',
    'S13_ATR_Break':  'ATR 변동성 돌파',
    'S14_Donchian':   'Donchian 채널 돌파',
    'S15_ZScore':     'Z-Score 평균회귀',
    'S16_SMA_Rev':    'SMA50 이탈 회귀',
    'S17_FVG':        'Fair Value Gap (ICT)',
    'S18_MSB':        'Market Structure Break',
    'S19_Monday':     '월요일 레인지 전략',
    'S20_InsideBar':  'Inside Bar 돌파',
    'S21_Engulfing':  '불리시 엔글핑',
    'S22_VolBreak':   '거래량 돌파',
    'S23_EMA_Ribbon': 'EMA 리본 정배열',
    'S24_CHoCH':      'CHoCH 추세전환',
    'S25_PinBar':     '핀바 망치형',
}

CONFLUENCE_DESC = {
    'C1_DBB_SmartMoney':   ('C1 DBB SmartMoney', 'DBB + FVG + MSB + VolBreak + Engulfing', '#e3b341'),
    'C2_MultiTrend':       ('C2 Multi-Trend',     'EMA9/21 + EMA20/50 + RSI + MACD + Ribbon', '#3fb950'),
    'C3_Breakout':         ('C3 Breakout',         'Donchian + ATR + BB상단 + Volume + GoldenX', '#58a6ff'),
    'C4_MeanReversion':    ('C4 Mean Reversion',   'RSI역추세 + BB하단 + ZScore + SMA + PinBar', '#ff7b72'),
    'C5_PatternStructure': ('C5 Pattern Structure','CHoCH + InsideBar + Engulfing + FVG + Ichimoku', '#bc8cff'),
}


def render():
    st.markdown("## Strategy Factory")
    st.markdown("25개 전략 + C1~C5 합류점 + FVG+OB — 종목별 현재 신호 현황")

    # 종목 선택
    ticker_list = list(ALL_ASSETS.keys())
    selected = st.selectbox("종목 선택", ticker_list,
                            format_func=lambda t: f"{t} — {ALL_ASSETS[t]['name']}")

    asset  = ALL_ASSETS[selected]
    market = asset['market']
    df = load(selected, market)

    if df is None or len(df) < 60:
        st.error("데이터 로드 실패 — 잠시 후 다시 시도해주세요")
        return

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors='coerce')

    price  = float(df['Close'].iloc[-1])
    pstrat = PRIMARY_STRATEGY[selected]

    # ── 전략 신호 계산 ────────────────────────────────────────
    try:
        all_sigs = get_all_signals(df)
    except Exception as e:
        st.error(f"전략 신호 계산 오류: {e}")
        return

    # ── 합류점 스코어 계산 ────────────────────────────────────
    try:
        c_scores = get_latest_scores(df)
    except Exception as e:
        c_scores = {}

    buy_cnt = sum(1 for v in all_sigs.values() if v == 1)

    # ── 상단 KPI ─────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    with k1: st.metric("현재가", f"{price:,.2f}")
    with k2: st.metric("매수 신호", f"{buy_cnt} / 25")
    with k3: st.metric("1순위 전략", pstrat,
                       delta="매수" if all_sigs.get(pstrat, 0) == 1 else "관망")
    with k4:
        active_c = sum(1 for k, v in c_scores.items() if v >= MIN_SCORE.get(k, 4))
        st.metric("활성 합류점", f"{active_c} / 5")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["FVG+OB + C1~C5 합류점", "25개 전략 신호", "전종목 히트맵"])

    # ── Tab1: FVG+OB + C1~C5 ──────────────────────────────────
    with tab1:
        st.markdown("### FVG+OB 핵심 전략")
        fvg_sig = all_sigs.get('S17_FVG', 0)
        ob_sig  = all_sigs.get('S18_MSB', 0)
        col_f, col_o = st.columns(2)
        with col_f:
            color = '#3fb950' if fvg_sig else '#30363d'
            st.markdown(f"""
            <div style='background:#1c2128;border:2px solid {color};border-radius:10px;
            padding:16px;text-align:center;'>
            <div style='font-size:18px;font-weight:700;color:{color};'>
            {"매수 신호" if fvg_sig else "관망"}</div>
            <div style='color:#8b949e;margin-top:6px;'>S17 FVG (Fair Value Gap)</div>
            <div style='color:#8b949e;font-size:12px;'>3봉 갭 불균형 되돌림</div>
            </div>""", unsafe_allow_html=True)
        with col_o:
            color2 = '#58a6ff' if ob_sig else '#30363d'
            st.markdown(f"""
            <div style='background:#1c2128;border:2px solid {color2};border-radius:10px;
            padding:16px;text-align:center;'>
            <div style='font-size:18px;font-weight:700;color:{color2};'>
            {"매수 신호" if ob_sig else "관망"}</div>
            <div style='color:#8b949e;margin-top:6px;'>S18 OB (Order Block / MSB)</div>
            <div style='color:#8b949e;font-size:12px;'>충격파 직전 되돌림</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### C1~C5 합류점 스코어")

        for cid, (cname, cdesc, ccolor) in CONFLUENCE_DESC.items():
            score    = c_scores.get(cid, 0)
            min_s    = MIN_SCORE.get(cid, 4)
            active   = score >= min_s
            bar_pct  = int(score / 5 * 100)
            act_color = ccolor if active else '#30363d'
            badge    = f"<span style='background:{ccolor};color:#000;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;'>ACTIVE</span>" if active else "<span style='background:#30363d;color:#8b949e;padding:2px 8px;border-radius:10px;font-size:11px;'>대기</span>"

            st.markdown(f"""
            <div style='background:#1c2128;border:1px solid {act_color};border-radius:8px;
            padding:12px 16px;margin:6px 0;'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
              <div>
                <span style='font-weight:700;color:{ccolor};'>{cname}</span>
                &nbsp;{badge}
                <div style='color:#8b949e;font-size:12px;margin-top:4px;'>{cdesc}</div>
              </div>
              <div style='text-align:right;'>
                <div style='font-size:24px;font-weight:700;color:{ccolor};'>{score}<span style='font-size:14px;color:#8b949e;'>/{5}</span></div>
                <div style='font-size:11px;color:#8b949e;'>기준: {min_s}이상</div>
              </div>
            </div>
            <div style='background:#21262d;border-radius:4px;height:6px;margin-top:8px;'>
              <div style='background:{ccolor};width:{bar_pct}%;height:6px;border-radius:4px;'></div>
            </div>
            </div>""", unsafe_allow_html=True)

    # ── Tab2: 25개 전략 ───────────────────────────────────────
    with tab2:
        rows = []
        for sname, sig in sorted(all_sigs.items()):
            is_primary = (sname == pstrat)
            rows.append({
                '구분': '★ 1순위' if is_primary else '',
                '전략코드': sname,
                '전략명': STRATEGY_DESC.get(sname, sname),
                '신호': '매수' if sig == 1 else '관망',
                '상태': sig,
            })
        df_t = pd.DataFrame(rows).sort_values('상태', ascending=False).reset_index(drop=True)
        df_t = df_t.drop(columns=['상태'])
        st.dataframe(df_t, use_container_width=True, hide_index=True,
                     column_config={'구분': st.column_config.TextColumn(width='small'),
                                    '신호': st.column_config.TextColumn(width='small')})

        # 매수/관망 도넛차트
        fig = go.Figure(go.Pie(
            values=[buy_cnt, 25 - buy_cnt],
            labels=['매수 신호', '관망'],
            hole=0.6,
            marker_colors=['#3fb950', '#30363d'],
        ))
        fig.update_layout(
            height=250, paper_bgcolor='rgba(0,0,0,0)',
            font_color='#e6edf3', margin=dict(t=10, b=10, l=10, r=10),
            showlegend=True, legend=dict(font_color='#e6edf3'),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Tab3: 전종목 히트맵 ───────────────────────────────────
    with tab3:
        st.markdown("전종목 × 전략 신호 히트맵 (초록=매수, 회색=관망)")
        with st.spinner("전종목 신호 계산 중... (30초 소요)"):
            heatmap_data = {}
            for t, ast in ALL_ASSETS.items():
                if ast['market'] == 'CRYPTO':
                    continue
                df2 = load(t, ast['market'])
                if df2 is None or len(df2) < 60: continue
                sigs2 = get_all_signals(df2)
                heatmap_data[t] = sigs2

        if heatmap_data:
            strategies = list(STRATEGY_DESC.keys())
            tickers    = list(heatmap_data.keys())
            z = [[heatmap_data[t].get(s, 0) for s in strategies] for t in tickers]
            tick_labels = [f"{t}({ALL_ASSETS[t]['name']})" for t in tickers]

            fig2 = go.Figure(go.Heatmap(
                z=z, x=strategies, y=tick_labels,
                colorscale=[[0, '#21262d'], [1, '#3fb950']],
                showscale=False, zmin=0, zmax=1,
            ))
            fig2.update_layout(
                height=max(300, len(tickers) * 35),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#e6edf3',
                margin=dict(t=10, b=100, l=120, r=10),
                xaxis=dict(tickangle=-45, color='#8b949e'),
                yaxis=dict(color='#8b949e'),
            )
            st.plotly_chart(fig2, use_container_width=True)
