# -*- coding: utf-8 -*-
"""
전략 팩토리 — 백테스팅 검증 25개 전략 신호 생성
반환: 1 (롱 진입), 0 (관망/청산)
"""
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings('ignore')

# ─── 지표 헬퍼 ──────────────────────────────────────────────
def _rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))

def _atr(df, n=14):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low']  - df['Close'].shift()).abs()
    return pd.concat([hl,hc,lc],axis=1).max(axis=1).ewm(span=n,adjust=False).mean()

def _wma(s, n):
    w = np.arange(1, n+1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, w)/w.sum(), raw=True)

def _supertrend(df, n=7, m=3):
    a = _atr(df, n); hl2 = (df['High']+df['Low'])/2
    ub = hl2+m*a; lb = hl2-m*a
    st = pd.Series(np.nan, index=df.index)
    for i in range(1, len(df)):
        if   df['Close'].iloc[i] > ub.iloc[i-1]: st.iloc[i] = 1
        elif df['Close'].iloc[i] < lb.iloc[i-1]: st.iloc[i] = -1
        else: st.iloc[i] = st.iloc[i-1] if not np.isnan(st.iloc[i-1]) else 1
    return st

# ─── 전략 신호 함수 ──────────────────────────────────────────
def get_signal(df: pd.DataFrame, strategy: str) -> int:
    """
    주어진 df(OHLCV)와 전략명으로 현재 신호 반환
    Returns: 1 (매수/유지), 0 (관망/청산)
    """
    if len(df) < 60:
        return 0

    c = df['Close']
    sigs = _compute_all(df)
    sig_series = sigs.get(strategy)
    if sig_series is None:
        return 0

    # 가장 최신 신호 반환
    return int(sig_series.iloc[-1]) if not pd.isna(sig_series.iloc[-1]) else 0

def get_all_signals(df: pd.DataFrame) -> dict:
    """모든 전략 신호를 {전략명: 현재값} 딕셔너리로 반환"""
    if len(df) < 60:
        return {}
    sigs = _compute_all(df)
    return {k: (int(v.iloc[-1]) if not pd.isna(v.iloc[-1]) else 0)
            for k, v in sigs.items()}

def _compute_all(df: pd.DataFrame) -> dict:
    c = df['Close']; out = {}
    e9  = c.ewm(span=9,  adjust=False).mean()
    e21 = c.ewm(span=21, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    e200= c.ewm(span=200,adjust=False).mean()
    s50 = c.rolling(50).mean()
    s200= c.rolling(200).mean()

    out['S01_EMA9_21']     = (e9>e21).astype(int).shift(1).fillna(0)
    out['S02_EMA20_50']    = (e21>e50).astype(int).shift(1).fillna(0)
    out['S03_GoldenCross'] = (s50>s200).astype(int).shift(1).fillna(0)
    out['S04_SuperTrend']  = (_supertrend(df)==1).astype(int).shift(1).fillna(0)

    hf = _wma(2*_wma(c,10)-_wma(c,20), max(1,int(np.sqrt(20))))
    hs = _wma(2*_wma(c,20)-_wma(c,40), max(1,int(np.sqrt(40))))
    out['S05_HullMA'] = (hf>hs).astype(int).shift(1).fillna(0)

    t9  = (df['High'].rolling(9).max() +df['Low'].rolling(9).min())/2
    k26 = (df['High'].rolling(26).max()+df['Low'].rolling(26).min())/2
    sa  = ((t9+k26)/2).shift(26)
    sb  = ((df['High'].rolling(52).max()+df['Low'].rolling(52).min())/2).shift(26)
    cloud = pd.concat([sa,sb],axis=1).max(axis=1)
    out['S06_Ichimoku'] = (c>cloud).astype(int).shift(1).fillna(0)

    r14 = _rsi(c)
    out['S07_RSI_Trend'] = (r14>50).astype(int).shift(1).fillna(0)

    p=pd.Series(0,index=df.index); inp=False
    for i in range(len(df)):
        v=r14.iloc[i]
        if pd.isna(v): p.iloc[i]=0; continue
        if not inp and v<35: inp=True
        elif inp and v>65: inp=False
        p.iloc[i]=1 if inp else 0
    out['S08_RSI_Rev'] = p.shift(1).fillna(0)

    m12=c.ewm(span=12,adjust=False).mean(); m26=c.ewm(span=26,adjust=False).mean()
    macd=m12-m26; msig=macd.ewm(span=9,adjust=False).mean()
    out['S09_MACD']     = (macd>msig).astype(int).shift(1).fillna(0)
    out['S10_MACDHist'] = (macd-msig>0).astype(int).shift(1).fillna(0)

    sm20=c.rolling(20).mean(); sd20=c.rolling(20).std()
    ub=sm20+2*sd20; lb=sm20-2*sd20
    out['S11_BB_Break'] = (c>ub).astype(int).shift(1).fillna(0)

    p2=pd.Series(0,index=df.index); i2=False
    for i in range(len(df)):
        if pd.isna(lb.iloc[i]): p2.iloc[i]=0; continue
        if not i2 and c.iloc[i]<lb.iloc[i]: i2=True
        elif i2 and c.iloc[i]>ub.iloc[i]: i2=False
        p2.iloc[i]=1 if i2 else 0
    out['S12_BB_Rev'] = p2.shift(1).fillna(0)

    a14=_atr(df); h20=df['High'].rolling(20).max().shift(1)
    out['S13_ATR_Break'] = (c>h20+a14*0.5).astype(int).shift(1).fillna(0)

    h20d=df['High'].rolling(20).max().shift(1); l20d=df['Low'].rolling(20).min().shift(1)
    p3=pd.Series(0,index=df.index); i3=False
    for i in range(len(df)):
        if pd.isna(h20d.iloc[i]): p3.iloc[i]=0; continue
        if not i3 and c.iloc[i]>h20d.iloc[i]: i3=True
        elif i3 and c.iloc[i]<l20d.iloc[i]: i3=False
        p3.iloc[i]=1 if i3 else 0
    out['S14_Donchian'] = p3.shift(1).fillna(0)

    zm=c.rolling(20).mean(); zs=c.rolling(20).std()
    zsc=(c-zm)/zs.replace(0,np.nan)
    p4=pd.Series(0,index=df.index); i4=False
    for i in range(len(df)):
        if pd.isna(zsc.iloc[i]): p4.iloc[i]=0; continue
        if not i4 and zsc.iloc[i]<-1.5: i4=True
        elif i4 and zsc.iloc[i]>0: i4=False
        p4.iloc[i]=1 if i4 else 0
    out['S15_ZScore'] = p4.shift(1).fillna(0)

    s50b=c.rolling(50).mean(); dev=(c-s50b)/s50b.replace(0,np.nan)
    p5=pd.Series(0,index=df.index); i5=False
    for i in range(len(df)):
        if pd.isna(dev.iloc[i]): p5.iloc[i]=0; continue
        if not i5 and dev.iloc[i]<-0.03: i5=True
        elif i5 and dev.iloc[i]>0.01: i5=False
        p5.iloc[i]=1 if i5 else 0
    out['S16_SMA_Rev'] = p5.shift(1).fillna(0)

    fvg=df['Low']>df['High'].shift(2)
    p6=pd.Series(0,index=df.index); i6=False
    for i in range(2,len(df)):
        lm=df['Low'].iloc[max(0,i-5):i].min()
        if not i6 and fvg.iloc[i]: i6=True
        elif i6 and c.iloc[i]<lm: i6=False
        p6.iloc[i]=1 if i6 else 0
    out['S17_FVG'] = p6.shift(1).fillna(0)

    sh=df['High'].rolling(10).max().shift(1)
    p7=pd.Series(0,index=df.index); i7=False
    for i in range(len(df)):
        if pd.isna(sh.iloc[i]): p7.iloc[i]=0; continue
        lm2=df['Low'].rolling(5).min().iloc[i] if not pd.isna(df['Low'].rolling(5).min().iloc[i]) else 0
        if not i7 and c.iloc[i]>sh.iloc[i]: i7=True
        elif i7 and c.iloc[i]<lm2: i7=False
        p7.iloc[i]=1 if i7 else 0
    out['S18_MSB'] = p7.shift(1).fillna(0)

    dow=pd.Series(df.index.dayofweek,index=df.index)
    p8=pd.Series(0,index=df.index); mh=ml=None; wk=None; i8=False
    for i in range(len(df)):
        d=dow.iloc[i]; wn=df.index[i].isocalendar()[:2]
        if d==0: mh=df['High'].iloc[i]; ml=df['Low'].iloc[i]; wk=wn; i8=False
        elif wk==wn and mh is not None:
            if not i8 and c.iloc[i]>mh: i8=True
            elif i8 and c.iloc[i]<ml: i8=False
        p8.iloc[i]=1 if i8 else 0
    out['S19_Monday'] = p8.shift(1).fillna(0)

    ph=df['High'].shift(1); pl=df['Low'].shift(1)
    ib=(df['High']<ph)&(df['Low']>pl); ibk=ib.shift(1)&(c>ph)
    p9=pd.Series(0,index=df.index); i9=False; h9=0
    for i in range(len(df)):
        if not i9 and ibk.iloc[i]: i9=True; h9=0
        elif i9: h9+=1
        if i9 and h9>=5: i9=False; h9=0
        p9.iloc[i]=1 if i9 else 0
    out['S20_InsideBar'] = p9.shift(1).fillna(0)

    pb_=c.shift(1)<df['Open'].shift(1); cb_=c>df['Open']
    eng=(df['Open']<c.shift(1))&(c>df['Open'].shift(1))
    be=pb_&cb_&eng
    pa=pd.Series(0,index=df.index); ia=False; ha=0
    for i in range(len(df)):
        if not ia and be.iloc[i]: ia=True; ha=0
        elif ia: ha+=1
        if ia and ha>=5: ia=False; ha=0
        pa.iloc[i]=1 if ia else 0
    out['S21_Engulfing'] = pa.shift(1).fillna(0)

    vol=df['Volume']; av=vol.rolling(20).mean(); h20v=df['High'].rolling(20).max().shift(1)
    if vol.sum()>0:
        out['S22_VolBreak']=((vol>av*1.5)&(c>h20v)).astype(int).shift(1).fillna(0)
    else:
        out['S22_VolBreak']=pd.Series(0,index=df.index)

    out['S23_EMA_Ribbon'] = ((e9>e21)&(e21>e50)&(e50>e200)).astype(int).shift(1).fillna(0)

    shc=df['High'].rolling(15).max().shift(15)
    pc=pd.Series(0,index=df.index); ic=False; hc=0
    for i in range(len(df)):
        if pd.isna(shc.iloc[i]): pc.iloc[i]=0; continue
        if not ic and c.iloc[i]>shc.iloc[i]: ic=True; hc=0
        elif ic: hc+=1
        if ic and hc>=10: ic=False
        pc.iloc[i]=1 if ic else 0
    out['S24_CHoCH'] = pc.shift(1).fillna(0)

    bd=(c-df['Open']).abs()
    lw=df[['Open','Close']].min(axis=1)-df['Low']
    uw=df['High']-df[['Open','Close']].max(axis=1)
    rg=df['High']-df['Low']
    hm=(lw>2*bd)&(uw<bd)&(rg>0)
    pb2=pd.Series(0,index=df.index); ib2=False; hb2=0
    for i in range(len(df)):
        if not ib2 and hm.iloc[i]: ib2=True; hb2=0
        elif ib2: hb2+=1
        if ib2 and hb2>=5: ib2=False; hb2=0
        pb2.iloc[i]=1 if ib2 else 0
    out['S25_PinBar'] = pb2.shift(1).fillna(0)

    return out
