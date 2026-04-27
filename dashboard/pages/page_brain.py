# -*- coding: utf-8 -*-
"""Market Brain 페이지 — 시장 국면 감지 (Bull/Bear/Neutral)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data.data_loader import load

REGIME_ASSETS = ['SPY','QQQ']

def detect_regime(df: pd.DataFrame) -> dict:
    """시장 국면 감지"""
    c  = df['Close']
    r  = c.pct_change()
    ma20  = c.rolling(20).mean().iloc[-1]
    ma50  = c.rolling(50).mean().iloc[-1]
    ma200 = c.rolling(200).mean().iloc[-1]
    vol20 = r.rolling(20).std().iloc[-1] * np.sqrt(252) * 100
    vol_avg = r.rolling(60).std().iloc[-1] * np.sqrt(252) * 100
    rsi14 = _rsi(c).iloc[-1]
    cur   = c.iloc[-1]

    score = 0
    score += 1 if cur > ma20  else -1
    score += 1 if cur > ma50  else -1
    score += 1 if cur > ma200 else -1
    score += 1 if ma20 > ma50 else -1
    score += 1 if rsi14 > 50  else -1

    if   score >= 3: regime = 'BULL';    color='#3fb950'; emoji='🐂'
    elif score <= -3: regime = 'BEAR';   color='#f85149'; emoji='🐻'
    else:             regime = 'NEUTRAL';color='#e3b341'; emoji='⚖️'

    return {
        'regime': regime, 'color': color, 'emoji': emoji,
        'score':  score, 'rsi': rsi14,
        'ma20': ma20, 'ma50': ma50, 'ma200': ma200,
        'vol20': vol20, 'vol_avg': vol_avg,
        'current': cur,
    }

def _rsi(s, n=14):
    d=s.diff(); g=d.clip(lower=0).ewm(com=n-1,min_periods=n).mean()
    l=(-d).clip(lower=0).ewm(com=n-1,min_periods=n).mean()
    return 100-100/(1+g/l.replace(0,np.nan))

def render():
    st.markdown("## 🧠 Market Brain — 시장 국면 감지")
    st.markdown("SPY·QQQ 데이터 기반으로 현재 시장이 Bull/Bear/Neutral 중 어디에 있는지 판단합니다.")

    col1, col2 = st.columns(2)

    for ticker, col in zip(REGIME_ASSETS, [col1, col2]):
        df = load(ticker, 'US')
        if df is None or len(df) < 60:
            with col:
                st.warning(f"{ticker} 데이터 로드 실패")
            continue

        r = detect_regime(df)
        c = df['Close']
        ma20  = c.rolling(20).mean()
        ma50  = c.rolling(50).mean()
        ma200 = c.rolling(200).mean()
        recent = df.tail(120)

        with col:
            st.markdown(f"""
            <div style='background:#1c2128;border:1px solid {r["color"]};border-radius:12px;
            padding:16px;text-align:center;margin-bottom:16px;'>
            <div style='font-size:48px;'>{r["emoji"]}</div>
            <div style='font-size:28px;font-weight:700;color:{r["color"]};'>{r["regime"]}</div>
            <div style='color:#8b949e;font-size:13px;'>{ticker} | 스코어: {r["score"]}/5</div>
            </div>
            """, unsafe_allow_html=True)

            # 지표 표
            metrics = {
                'RSI(14)':      f"{r['rsi']:.1f}",
                '현재가':        f"{r['current']:.2f}",
                'MA20':         f"{r['ma20']:.2f}",
                'MA50':         f"{r['ma50']:.2f}",
                'MA200':        f"{r['ma200']:.2f}",
                '변동성(연)':   f"{r['vol20']:.1f}%",
            }
            df_m = pd.DataFrame({'지표': list(metrics.keys()), '값': list(metrics.values())})
            st.dataframe(df_m, use_container_width=True, hide_index=True)

            # 차트
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=recent.index, open=recent['Open'], high=recent['High'],
                low=recent['Low'], close=recent['Close'], name=ticker,
                increasing_line_color='#3fb950', decreasing_line_color='#f85149',
            ))
            fig.add_trace(go.Scatter(x=recent.index, y=ma20.reindex(recent.index),
                line=dict(color='#e3b341',width=1.5), name='MA20'))
            fig.add_trace(go.Scatter(x=recent.index, y=ma50.reindex(recent.index),
                line=dict(color='#58a6ff',width=1.5), name='MA50'))
            fig.add_trace(go.Scatter(x=recent.index, y=ma200.reindex(recent.index),
                line=dict(color='#ff7b72',width=1.5), name='MA200'))
            fig.update_layout(
                height=300, paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(13,17,23,0.8)',
                font_color='#e6edf3', showlegend=True,
                margin=dict(t=10,b=30,l=40,r=10),
                xaxis=dict(gridcolor='#21262d',color='#8b949e',rangeslider=dict(visible=False)),
                yaxis=dict(gridcolor='#21262d',color='#8b949e'),
                legend=dict(font=dict(color='#8b949e'),bgcolor='rgba(0,0,0,0)'),
            )
            st.plotly_chart(fig, use_container_width=True)

    # 시장 국면 전략 추천
    st.markdown("---")
    st.markdown("#### 💡 국면별 전략 추천")
    df_rec = pd.DataFrame([
        {'국면':'🐂 BULL','추천전략':'S01_EMA9_21, S02_EMA20_50, S23_EMA_Ribbon','설명':'추세 추종이 유리한 강세장'},
        {'국면':'🐻 BEAR','추천전략':'S12_BB_Rev, S15_ZScore, S08_RSI_Rev','설명':'평균회귀 전략으로 반등 포착'},
        {'국면':'⚖️ NEUTRAL','추천전략':'S07_RSI_Trend, S09_MACD, S19_Monday','설명':'범위 매매와 모멘텀 혼용'},
    ])
    st.dataframe(df_rec, use_container_width=True, hide_index=True)
