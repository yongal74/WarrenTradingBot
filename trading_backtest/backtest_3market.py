# -*- coding: utf-8 -*-
"""
KR5 + US5 + CRYPTO5 전종목
FVG+OB 단독  vs  FVG+OB+DBB
15분봉, R:R=1:2, 시드 1000만원 기준 월 수익 환산
"""
import sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ── 파라미터 ─────────────────────────────────────────────────
RR           = 2.0
MAX_SL_PCT   = 0.015
MIN_SL_PCT   = 0.001
ZONE_EXPIRE  = 20
MAX_HOLD     = 32       # 봉 기준
CAPITAL      = 10_000_000
RISK_PCT     = 0.01     # 거래당 리스크 1%

UNIVERSES = {
    'KR': {
        '005930': ('삼성전자',    '005930.KS'),
        '000660': ('SK하이닉스', '000660.KS'),
        '009150': ('삼성전기',   '009150.KS'),
        '034020': ('두산에너빌','034020.KS'),
        '008060': ('대덕전자',   '008060.KS'),
    },
    'US': {
        'NVDA': ('엔비디아',  'NVDA'),
        'PLTR': ('팔란티어', 'PLTR'),
        'AMD':  ('AMD',       'AMD'),
        'TSLA': ('테슬라',    'TSLA'),
        'SOXX': ('반도체ETF', 'SOXX'),
    },
    'CRYPTO': {
        'BTC': ('비트코인',  'BTC-USD'),
        'ETH': ('이더리움', 'ETH-USD'),
        'SOL': ('솔라나',    'SOL-USD'),
        'XRP': ('리플',      'XRP-USD'),
        'BNB': ('바이낸스',  'BNB-USD'),
    },
}


def _load(yf_ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.download(yf_ticker, period='60d', interval='15m',
                         auto_adjust=True, progress=False, multi_level_index=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        df = df[['Open','High','Low','Close','Volume']].dropna()
        return df if len(df) >= 100 else None
    except: return None


def _dbb_bull(df: pd.DataFrame) -> pd.Series:
    """DBB Bull zone: Close > 20MA + 1std (shift(1)로 미래참조 방지)"""
    ma  = df['Close'].rolling(20).mean()
    std = df['Close'].rolling(20).std()
    return (df['Close'].shift(1) > (ma + std).shift(1)).astype(int)


def _detect_fvg(df):
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG','formed_i':i,
                          'zone_high':lo0,'zone_low':hi2,'expire_i':i+ZONE_EXPIRE})
    return zones


def _detect_ob(df):
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        imp = float(df['High'].iloc[i+1:i+3].max())
        if (imp - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB','formed_i':i,
                          'zone_high':float(b['High']),'zone_low':float(b['Low']),
                          'expire_i':i+ZONE_EXPIRE})
    return zones


def backtest(df: pd.DataFrame, use_dbb: bool) -> dict:
    dbb = _dbb_bull(df) if use_dbb else None
    zones = sorted(_detect_fvg(df) + _detect_ob(df), key=lambda z: z['formed_i'])

    trades, active = [], []
    in_pos = False
    entry_p = tp_p = sl_p = 0.0
    entry_i = 0
    ztype = ''

    for i in range(3, len(df)):
        bar = df.iloc[i]
        hi, lo, op, cl = float(bar['High']), float(bar['Low']), float(bar['Open']), float(bar['Close'])

        for z in zones:
            if z['formed_i'] == i - 1: active.append(z)
        active = [z for z in active if z['expire_i'] > i]

        if in_pos:
            if op <= sl_p:
                trades.append((ztype, (op-entry_p)/entry_p*100, 'SL_GAP'))
                in_pos = False; continue
            if hi >= tp_p:
                trades.append((ztype, (tp_p-entry_p)/entry_p*100, 'TP'))
                in_pos = False; continue
            if lo <= sl_p:
                trades.append((ztype, (sl_p-entry_p)/entry_p*100, 'SL'))
                in_pos = False; continue
            if i - entry_i >= MAX_HOLD:
                trades.append((ztype, (cl-entry_p)/entry_p*100, 'MAX'))
                in_pos = False; continue

        if not in_pos:
            if use_dbb and int(dbb.iloc[i]) != 1: continue
            for z in active[:]:
                zh, zl = z['zone_high'], z['zone_low']
                if lo <= zh and cl >= zl:
                    ep = min(op, zh) if op <= zh else zh
                    sl_pct = (ep - zl) / ep
                    if not (MIN_SL_PCT <= sl_pct <= MAX_SL_PCT): continue
                    sl_p = ep - ep * sl_pct
                    tp_p = ep + ep * sl_pct * RR
                    entry_p, entry_i, in_pos, ztype = ep, i, True, z['type']
                    active.remove(z); break

    if in_pos:
        cl = float(df['Close'].iloc[-1])
        trades.append((ztype, (cl-entry_p)/entry_p*100, 'END'))

    if len(trades) < 3:
        return {'n':0,'wr':0,'ev':0,'pf':0,'fvg_wr':0,'ob_wr':0,
                'avg_w':0,'avg_l':0,'monthly_pnl':0,'n_per_month':0}

    pnls   = [t[1] for t in trades]
    types  = [t[0] for t in trades]
    wins   = [p for p in pnls if p > 0]
    loses  = [p for p in pnls if p <= 0]
    n      = len(pnls)
    wr     = len(wins) / n * 100
    avg_w  = float(np.mean(wins))  if wins  else 0.0
    avg_l  = float(np.mean(loses)) if loses else 0.0
    ev     = (wr/100)*avg_w + (1-wr/100)*avg_l
    gp     = sum(wins)
    gl     = abs(sum(loses)) if loses else 1e-9
    pf     = round(gp/gl, 2)

    fvg_p  = [p for t,p,_ in trades if t=='FVG']
    ob_p   = [p for t,p,_ in trades if t=='OB']
    fvg_wr = round(sum(1 for p in fvg_p if p>0)/len(fvg_p)*100,1) if fvg_p else 0
    ob_wr  = round(sum(1 for p in ob_p  if p>0)/len(ob_p )*100,1) if ob_p  else 0

    # 월 수익 환산: 약 40거래일 데이터 → 월 22거래일 기준
    n_per_month  = n / (40/22)
    sl_est       = abs(avg_l) / RR / 100 if avg_l != 0 else 0.005
    pos_size     = min(CAPITAL * RISK_PCT / sl_est if sl_est > 0 else CAPITAL*0.1, CAPITAL*0.2)
    monthly_pnl  = pos_size * (ev/100) * n_per_month

    return {
        'n': n, 'wr': round(wr,1), 'ev': round(ev,3),
        'pf': pf, 'fvg_wr': fvg_wr, 'ob_wr': ob_wr,
        'avg_w': round(avg_w,3), 'avg_l': round(avg_l,3),
        'n_per_month': round(n_per_month,1),
        'monthly_pnl': round(monthly_pnl),
    }


def run():
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"\n{'='*72}")
    print(f"  FVG+OB  vs  FVG+OB+DBB  전종목 비교  [{stamp}]")
    print(f"  15분봉 R:R=1:{RR}  |  시드 {CAPITAL//10000:,}만원  |  거래당 리스크 {RISK_PCT*100:.0f}%")
    print(f"{'='*72}")

    summary = []

    for market, tickers in UNIVERSES.items():
        print(f"\n  ── {market} ──────────────────────────────────────────")
        print(f"  {'종목':<10} │ {'── FVG+OB 단독 ──':^36} │ {'── FVG+OB+DBB ──':^36} │ 추천")
        print(f"  {'':─<10}─┼─{'':─<36}─┼─{'':─<36}─┼─────")

        mkt_pnl_a = mkt_pnl_b = 0

        for code, (name, yf_tk) in tickers.items():
            df = _load(yf_tk)
            if df is None:
                print(f"  {name[:8]:<10} │ 데이터없음")
                continue

            ra = backtest(df, use_dbb=False)
            rb = backtest(df, use_dbb=True)

            mkt_pnl_a += ra['monthly_pnl']
            mkt_pnl_b += rb['monthly_pnl']

            best = 'A' if ra['ev'] >= rb['ev'] else 'B'
            star = '★FVG+OB' if best=='A' else '★+DBB  '

            fa = f"n={ra['n']:>2} WR={ra['wr']:>4.0f}% EV={ra['ev']:>+5.2f}% {ra['monthly_pnl']:>+8,.0f}원"
            fb = f"n={rb['n']:>2} WR={rb['wr']:>4.0f}% EV={rb['ev']:>+5.2f}% {rb['monthly_pnl']:>+8,.0f}원"
            print(f"  {name[:8]:<10} │ {fa} │ {fb} │ {star}")

            summary.append({
                'market': market, 'code': code, 'name': name,
                'A_n': ra['n'], 'A_wr': ra['wr'], 'A_ev': ra['ev'],
                'A_pnl': ra['monthly_pnl'],
                'B_n': rb['n'], 'B_wr': rb['wr'], 'B_ev': rb['ev'],
                'B_pnl': rb['monthly_pnl'],
                'best': best,
            })

        print(f"  {'':─<10}─┴─{'':─<36}─┴─{'':─<36}─┴─────")
        print(f"  {market} 합산 월 수익 │ FVG+OB: {mkt_pnl_a:>+10,.0f}원 │ +DBB: {mkt_pnl_b:>+10,.0f}원")

    # 전체 요약
    df_s = pd.DataFrame(summary)
    print(f"\n{'='*72}")
    print(f"  전체 합산 (3시장, 시드 각 1000만원)")
    print(f"{'='*72}")
    for mkt in ['KR','US','CRYPTO']:
        m = df_s[df_s['market']==mkt]
        if m.empty: continue
        va, vb = m['A_pnl'].sum(), m['B_pnl'].sum()
        better = 'FVG+OB' if va >= vb else 'FVG+OB+DBB'
        print(f"  {mkt:<7} │ FVG+OB: {va:>+10,.0f}원/월 │ +DBB: {vb:>+10,.0f}원/월 │ → {better}")

    total_a = df_s['A_pnl'].sum()
    total_b = df_s['B_pnl'].sum()
    print(f"  {'':─<68}")
    print(f"  합계    │ FVG+OB: {total_a:>+10,.0f}원/월 │ +DBB: {total_b:>+10,.0f}원/월")
    print(f"\n  종목별 추천 전략:")
    for _, r in df_s.iterrows():
        rec = 'FVG+OB' if r['best']=='A' else 'FVG+OB+DBB'
        ev  = r['A_ev'] if r['best']=='A' else r['B_ev']
        pnl = r['A_pnl'] if r['best']=='A' else r['B_pnl']
        wr  = r['A_wr'] if r['best']=='A' else r['B_wr']
        print(f"  [{r['market']}] {r['name']:<8} → {rec:<12} WR={wr:.0f}% EV={ev:+.2f}% 월{pnl:>+8,.0f}원")

    print(f"\n  ★ 시드 3000만원 합산 예상 월 수익:")
    print(f"     FVG+OB     : {total_a:>+,.0f}원/월")
    print(f"     FVG+OB+DBB : {total_b:>+,.0f}원/월")
    print(f"{'='*72}\n")

    # CSV 저장
    out = Path(__file__).parent.parent / 'backtest_results' / f'3market_compare_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    out.parent.mkdir(exist_ok=True)
    df_s.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"  결과 저장: {out}\n")


if __name__ == '__main__':
    run()
