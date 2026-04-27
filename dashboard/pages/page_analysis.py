# -*- coding: utf-8 -*-
"""Asset Analysis 페이지 — 개별 종목 기술분석"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config.assets import ALL_ASSETS
from data.data_loader import load

def render():
    st.markdown("## 🔬 Asset Analysis")

    col1, col2 = st.columns([2, 1])
    with col1:
        ticker = st.selectbox("종목 선택", list(ALL_ASSETS.keys()),
                              format_func=lambda t: f"{t} — {ALL_ASSETS[t]['name']}")
    with col2:
        period = st.selectbox("기간", ['3개월','6개월','1년','전체'], index=2)

    asset  = ALL_ASSETS[ticker]
    df = load(ticker, asset['market'])

    if df is None or len(df) < 30:
        st.error("데이터 로드 실패"); return

    # 기간 필터
    period_map = {'3개월':63, '6개월':126, '1년':252, '전체':len(df)}
    df = df.tail(period_map[period]).copy()

    # 지표 계산
    c = df['Close']
    df['MA20']  = c.rolling(20).mean()
    df['MA50']  = c.rolling(50).mean()
    df['MA200'] = c.rolling(200).mean()
    df['BB_upper'] = df['MA20'] + 2*c.rolling(20).std()
    df['BB_lower'] = df['MA20'] - 2*c.rolling(20).std()
    df['RSI']  = _rsi(c)
    df['MACD'] = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Hist']   = df['MACD'] - df['Signal']

    # 현재가 요약
    cur   = float(c.iloc[-1])
    prev  = float(c.iloc[-2]) if len(c)>1 else cur
    chg   = (cur-prev)/prev*100
    hi52  = float(df['High'].max())
    lo52  = float(df['Low'].min())
    vol   = float(df['Volume'].iloc[-1]) if df['Volume'].sum()>0 else 0

    kc1,kc2,kc3,kc4 = st.columns(4)
    with kc1: st.metric("현재가", f"{cur:,.2f}", f"{chg:+.2f}%")
    with kc2: st.metric("52주 최고", f"{hi52:,.2f}")
    with kc3: st.metric("52주 최저", f"{lo52:,.2f}")
    with kc4: st.metric("RSI(14)", f"{df['RSI'].iloc[-1]:.1f}")

    # 메인 차트 (캔들 + 볼린저 + MA)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20],
        vertical_spacing=0.03,
    )
    # 캔들
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name=ticker,
        increasing_line_color='#3fb950', decreasing_line_color='#f85149',
    ), row=1, col=1)
    # MA
    for ma,col in [('MA20','#e3b341'),('MA50','#58a6ff'),('MA200','#ff7b72')]:
        fig.add_trace(go.Scatter(x=df.index, y=df[ma],
            line=dict(color=col, width=1.5), name=ma), row=1, col=1)
    # BB
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_upper'],
        line=dict(color='#8b949e',width=1,dash='dot'), name='BB Upper',
        showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_lower'],
        line=dict(color='#8b949e',width=1,dash='dot'), name='BB Lower',
        fill='tonexty', fillcolor='rgba(139,148,158,0.05)',
        showlegend=False), row=1, col=1)
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'],
        line=dict(color='#e3b341',width=1.5), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line=dict(color='#f85149',dash='dot',width=1), row=2, col=1)
    fig.add_hline(y=30, line=dict(color='#3fb950',dash='dot',width=1), row=2, col=1)
    fig.add_hline(y=50, line=dict(color='#8b949e',dash='dot',width=0.5), row=2, col=1)
    # MACD
    colors = ['#3fb950' if h>=0 else '#f85149' for h in df['Hist']]
    fig.add_trace(go.Bar(x=df.index, y=df['Hist'],
        marker_color=colors, name='MACD Hist', showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'],
        line=dict(color='#58a6ff',width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'],
        line=dict(color='#ff7b72',width=1.5), name='Signal'), row=3, col=1)

    fig.update_layout(
        height=650, paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(13,17,23,0.8)', font_color='#e6edf3',
        margin=dict(t=10,b=30,l=50,r=10),
        legend=dict(bgcolor='rgba(0,0,0,0)',font=dict(color='#8b949e')),
        xaxis3=dict(rangeslider=dict(visible=False)),
    )
    for i in [1,2,3]:
        fig.update_xaxes(gridcolor='#21262d', color='#8b949e', row=i, col=1)
        fig.update_yaxes(gridcolor='#21262d', color='#8b949e', row=i, col=1)

    st.plotly_chart(fig, use_container_width=True)

def _rsi(s, n=14):
    d=s.diff(); g=d.clip(lower=0).ewm(com=n-1,min_periods=n).mean()
    l=(-d).clip(lower=0).ewm(com=n-1,min_periods=n).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
