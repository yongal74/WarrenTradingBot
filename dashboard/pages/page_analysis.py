# -*- coding: utf-8 -*-
"""Asset Analysis — TradingView급 캔들차트 + FVG/OB 구간 시각화"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config.assets import ALL_ASSETS
from data.data_loader import load, load_intraday


# ── 지표 계산 ─────────────────────────────────────────────────────
def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low']  - df['Close'].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(span=n, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    tp  = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, np.nan)
    return (tp * vol).cumsum() / vol.cumsum()


def _detect_fvg(df: pd.DataFrame) -> list:
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type': 'FVG', 'idx': i, 'high': lo0, 'low': hi2,
                          'x': df.index[i], 'x_end': df.index[min(i+20, len(df)-1)]})
    return zones[-8:]  # 최근 8개만


def _detect_ob(df: pd.DataFrame) -> list:
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']):
            continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type': 'OB', 'idx': i, 'high': float(b['High']),
                          'low': float(b['Low']),
                          'x': df.index[i], 'x_end': df.index[min(i+20, len(df)-1)]})
    return zones[-8:]


@st.cache_data(ttl=300)
def _load_cached(ticker: str, market: str, interval: str) -> pd.DataFrame | None:
    if interval == '1d':
        return load(ticker, market)
    return load_intraday(ticker, interval)


def render():
    # ── 컨트롤 바 ─────────────────────────────────────────────
    ctrl = st.columns([3, 1, 1, 1, 1, 1])
    with ctrl[0]:
        ticker = st.selectbox("종목", list(ALL_ASSETS.keys()),
                              format_func=lambda t: f"{t} — {ALL_ASSETS[t]['name']}",
                              label_visibility='collapsed')
    with ctrl[1]:
        interval = st.selectbox("봉 종류", ['15m','5m','1h','1d'],
                                label_visibility='collapsed')
    with ctrl[2]:
        show_fvg = st.checkbox("FVG", value=True)
    with ctrl[3]:
        show_ob  = st.checkbox("OB",  value=True)
    with ctrl[4]:
        show_vwap = st.checkbox("VWAP", value=True)
    with ctrl[5]:
        show_bb  = st.checkbox("BB", value=True)

    asset  = ALL_ASSETS[ticker]
    market = asset['market']

    with st.spinner("데이터 로딩..."):
        df = _load_cached(ticker, market, interval)

    if df is None or len(df) < 30:
        st.error("데이터 로드 실패 — 잠시 후 다시 시도하세요")
        return

    # 최근 300봉만 표시
    df = df.tail(300).copy()

    # 지표
    c = df['Close']
    ema9   = c.ewm(span=9,  adjust=False).mean()
    ema21  = c.ewm(span=21, adjust=False).mean()
    ema50  = c.ewm(span=50, adjust=False).mean()
    ma20   = c.rolling(20).mean()
    std20  = c.rolling(20).std()
    bb_up  = ma20 + 2 * std20
    bb_lo  = ma20 - 2 * std20
    rsi    = _rsi(c)
    macd   = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    msig   = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - msig
    vwap   = _vwap(df)
    atr_v  = _atr(df).iloc[-1]

    # FVG / OB 구간 감지
    fvg_zones = _detect_fvg(df) if show_fvg else []
    ob_zones  = _detect_ob(df)  if show_ob  else []

    # ── 현재가 요약 바 ─────────────────────────────────────────
    cur   = float(c.iloc[-1])
    prev  = float(c.iloc[-2]) if len(c) > 1 else cur
    chg   = (cur - prev) / prev * 100
    hi    = float(df['High'].max())
    lo    = float(df['Low'].min())
    vol   = float(df['Volume'].iloc[-1]) if df['Volume'].sum() > 0 else 0
    rsi_v = float(rsi.iloc[-1]) if not rsi.isna().all() else 50

    chg_col = '#26a69a' if chg >= 0 else '#ef5350'
    rsi_col = '#ef5350' if rsi_v > 70 else ('#26a69a' if rsi_v < 30 else '#d1d4dc')

    ks = ['현재가','등락','고가','저가','거래량','RSI(14)','ATR(14)','VWAP']
    vfmt = {
        '현재가': f"{cur:,.2f}",
        '등락':   f"{chg:+.2f}%",
        '고가':   f"{hi:,.2f}",
        '저가':   f"{lo:,.2f}",
        '거래량': f"{vol:,.0f}",
        'RSI(14)':f"{rsi_v:.1f}",
        'ATR(14)':f"{atr_v:.2f}",
        'VWAP':   f"{float(vwap.iloc[-1]):,.2f}" if not vwap.isna().all() else "N/A",
    }
    vcol = {
        '현재가': chg_col, '등락': chg_col, '고가': '#d1d4dc', '저가': '#d1d4dc',
        '거래량': '#d1d4dc', 'RSI(14)': rsi_col, 'ATR(14)': '#d1d4dc', 'VWAP': '#d1d4dc',
    }
    cols = st.columns(8)
    for col, k in zip(cols, ks):
        col.markdown(f"""<div class='kpi-card' style='padding:6px 10px;'>
        <div style='font-size:14px;font-weight:700;color:{vcol[k]};'>{vfmt[k]}</div>
        <div class='kpi-label'>{k}</div></div>""", unsafe_allow_html=True)

    # ── 메인 차트 ──────────────────────────────────────────────
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        vertical_spacing=0.01,
        subplot_titles=('', '거래량', 'RSI', 'MACD'),
    )

    # 캔들스틱
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'],  close=df['Close'],
        name=ticker,
        increasing=dict(line=dict(color='#26a69a', width=1), fillcolor='#26a69a'),
        decreasing=dict(line=dict(color='#ef5350', width=1), fillcolor='#ef5350'),
        whiskerwidth=0.3,
    ), row=1, col=1)

    # EMA lines
    for ema, col, w in [(ema9,'#ffb74d',1.2),(ema21,'#42a5f5',1.2),(ema50,'#ec407a',1.2)]:
        n = {id(ema9):'EMA9', id(ema21):'EMA21', id(ema50):'EMA50'}[id(ema)]
        fig.add_trace(go.Scatter(x=df.index, y=ema, line=dict(color=col,width=w),
                                 name=n, showlegend=True), row=1, col=1)

    # Bollinger Bands
    if show_bb:
        fig.add_trace(go.Scatter(x=df.index, y=bb_up, line=dict(color='#546e7a',width=0.8,dash='dot'),
                                 name='BB Upper', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bb_lo, line=dict(color='#546e7a',width=0.8,dash='dot'),
                                 name='BB Lower', fill='tonexty',
                                 fillcolor='rgba(84,110,122,0.06)', showlegend=False), row=1, col=1)

    # VWAP
    if show_vwap and not vwap.isna().all():
        fig.add_trace(go.Scatter(x=df.index, y=vwap, line=dict(color='#ce93d8',width=1.2,dash='dash'),
                                 name='VWAP', showlegend=True), row=1, col=1)

    # FVG 구간 하이라이트 (초록 반투명)
    for z in fvg_zones:
        fig.add_shape(type='rect',
                      x0=z['x'], x1=z['x_end'], y0=z['low'], y1=z['high'],
                      line=dict(width=0),
                      fillcolor='rgba(38,166,154,0.18)',
                      row=1, col=1)
        fig.add_annotation(x=z['x'], y=z['high'], text='FVG',
                           font=dict(size=9, color='#26a69a'),
                           showarrow=False, yanchor='bottom', row=1, col=1)

    # OB 구간 하이라이트 (파란 반투명)
    for z in ob_zones:
        fig.add_shape(type='rect',
                      x0=z['x'], x1=z['x_end'], y0=z['low'], y1=z['high'],
                      line=dict(width=0),
                      fillcolor='rgba(33,150,243,0.18)',
                      row=1, col=1)
        fig.add_annotation(x=z['x'], y=z['high'], text='OB',
                           font=dict(size=9, color='#42a5f5'),
                           showarrow=False, yanchor='bottom', row=1, col=1)

    # 거래량 바
    vol_colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ef5350'
                  for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'],
                         marker_color=vol_colors, name='Volume',
                         showlegend=False), row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=rsi,
                             line=dict(color='#ffd54f', width=1.2), name='RSI',
                             showlegend=False), row=3, col=1)
    for level, col in [(70,'#ef5350'),(30,'#26a69a'),(50,'#363a45')]:
        fig.add_hline(y=level, line=dict(color=col, dash='dot', width=0.8), row=3, col=1)
    # RSI 과매수/과매도 영역
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(239,83,80,0.05)', line_width=0, row=3, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor='rgba(38,166,154,0.05)', line_width=0, row=3, col=1)

    # MACD
    hist_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in hist]
    fig.add_trace(go.Bar(x=df.index, y=hist, marker_color=hist_colors,
                         name='MACD Hist', showlegend=False), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd,
                             line=dict(color='#42a5f5',width=1.2), name='MACD',
                             showlegend=False), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=msig,
                             line=dict(color='#ef5350',width=1.2), name='Signal',
                             showlegend=False), row=4, col=1)

    # 레이아웃
    _axis = dict(gridcolor='#1e222d', zeroline=False, color='#787b86',
                 tickfont=dict(size=10), showgrid=True)
    fig.update_layout(
        height=640,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#131722',
        font=dict(color='#787b86', size=11),
        margin=dict(t=4, b=4, l=4, r=4),
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=10, color='#787b86'),
                    orientation='h', x=0, y=1.02),
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        hoverlabel=dict(bgcolor='#1e222d', font=dict(size=11, color='#d1d4dc'),
                        bordercolor='#363a45'),
    )
    for r in [1, 2, 3, 4]:
        fig.update_xaxes(**_axis, row=r, col=1)
        fig.update_yaxes(**_axis, row=r, col=1)

    fig.update_yaxes(title_text='RSI', row=3, col=1, range=[0, 100])

    st.plotly_chart(fig, width='stretch', config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['select2d','lasso2d'],
        'displaylogo': False,
    })

    # ── FVG / OB 감지 목록 ────────────────────────────────────
    det1, det2 = st.columns(2)

    with det1:
        st.markdown("<div class='sec-hdr'>감지된 FVG 구간</div>", unsafe_allow_html=True)
        if fvg_zones:
            fvg_df = pd.DataFrame([
                {'구간 고가': f"{z['high']:.4f}", '구간 저가': f"{z['low']:.4f}",
                 '형성 시점': str(z['x'])[:16]} for z in fvg_zones
            ])
            st.dataframe(fvg_df, width='stretch', hide_index=True)
        else:
            st.info("FVG 구간 없음")

    with det2:
        st.markdown("<div class='sec-hdr'>감지된 OB 구간</div>", unsafe_allow_html=True)
        if ob_zones:
            ob_df = pd.DataFrame([
                {'구간 고가': f"{z['high']:.4f}", '구간 저가': f"{z['low']:.4f}",
                 '형성 시점': str(z['x'])[:16]} for z in ob_zones
            ])
            st.dataframe(ob_df, width='stretch', hide_index=True)
        else:
            st.info("OB 구간 없음")
