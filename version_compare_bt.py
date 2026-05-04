# -*- coding: utf-8 -*-
"""
단타 버전별 수익률 비교 백테스트 (2026-04-28)

V1 [기존]       : SL 0.5% / TP 1.0% / 품질필터 없음 / 5m확인 없음
V2 [중간]       : SL 1.0% / TP 2%(KR·US) 3%(CRYPTO) / 품질4점+Vol_Spike+Body_In_Zone / 5m확인 없음
V3 [최종 현재]  : V2 + 5m 양봉 확인 캔들 ON

비교 항목: 건수 / 승률 / 수수료 전 수익 / 수수료 후 수익 / EV/트레이드 / MDD
"""
import sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ── 수수료 (왕복) ─────────────────────────────────────────────
FEE = {'KR': 0.0023, 'US': 0.0050, 'CRYPTO': 0.0010}

# ── 유니버스 (ticker: name, yf_symbol, market) ───────────────
UNIVERSE_15M = {
    '005930': ('삼성전자',    '005930.KS', 'KR'),
    '000660': ('SK하이닉스', '000660.KS', 'KR'),
    '009150': ('삼성전기',   '009150.KS', 'KR'),
    '034020': ('두산에너빌', '034020.KS', 'KR'),
    '008060': ('대덕전자',   '008060.KS', 'KR'),
    'NVDA':   ('엔비디아',   'NVDA',      'US'),
    'PLTR':   ('팔란티어',   'PLTR',      'US'),
    'AMD':    ('AMD',        'AMD',       'US'),
    'TSLA':   ('테슬라',     'TSLA',      'US'),
    'SOXX':   ('반도체ETF',  'SOXX',      'US'),
    'BTC':    ('비트코인',   'BTC-USD',   'CRYPTO'),
    'ETH':    ('이더리움',   'ETH-USD',   'CRYPTO'),
    'SOL':    ('솔라나',     'SOL-USD',   'CRYPTO'),
    'XRP':    ('리플',       'XRP-USD',   'CRYPTO'),
}

ZONE_EXPIRE = 20   # 봉 기준 존 유효기간

# ────────────────────────────────────────────────────────────
# 공통 유틸
# ────────────────────────────────────────────────────────────
def _load_15m(yf_tk: str) -> pd.DataFrame | None:
    period = '5d' if 'KS' not in yf_tk else '5d'
    try:
        df = yf.download(yf_tk, period='60d', interval='15m',
                         auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return None


def _load_5m(yf_tk: str) -> pd.DataFrame | None:
    try:
        df = yf.download(yf_tk, period='5d', interval='5m',
                         auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if hasattr(df.columns, 'levels'): df.columns = df.columns.droplevel(1)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return None


def _detect_fvg(df):
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df['High'].iloc[i-2])
        lo0 = float(df['Low'].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > 0.0005:
            zones.append({'type':'FVG','formed_i':i,
                          'zone_high':lo0,'zone_low':hi2,
                          'expire_i':i+ZONE_EXPIRE})
    return zones


def _detect_ob(df):
    zones = []
    for i in range(1, len(df)-2):
        b = df.iloc[i]
        if float(b['Close']) >= float(b['Open']): continue
        impulse = float(df['High'].iloc[i+1:i+3].max())
        if (impulse - float(b['High'])) / float(b['High']) > 0.003:
            zones.append({'type':'OB','formed_i':i,
                          'zone_high':float(b['High']),'zone_low':float(b['Low']),
                          'expire_i':i+ZONE_EXPIRE})
    return zones


def _quality_flags(df: pd.DataFrame, entry: float, zone_low: float):
    """Vol_Spike + Body_In_Zone 여부만 반환 (1순위 필터용)"""
    if len(df) < 20:
        return False, False
    vol = df['Volume']
    avg_vol = vol.rolling(20).mean().iloc[-1] if len(vol) >= 20 else vol.mean()
    has_vol_spike = bool(avg_vol > 0 and vol.iloc[-1] > avg_vol * 1.5)

    bar = df.iloc[-1]
    op  = float(bar['Open'])
    cl  = float(bar['Close'])
    body_low  = min(op, cl)
    body_high = max(op, cl)
    has_body_in_zone = (body_high >= zone_low) and (body_low <= float(bar['High']))
    return has_vol_spike, has_body_in_zone


def _zone_mid_ok(df: pd.DataFrame, zone_low: float, zone_high: float) -> bool:
    """2순위: Close >= zone_mid"""
    cl = float(df['Close'].iloc[-1])
    zone_mid = zone_low + (zone_high - zone_low) * 0.5
    return cl >= zone_mid


def _5m_confirm(df5: pd.DataFrame | None, zone_low: float, zone_high: float) -> bool:
    if df5 is None or len(df5) < 2:
        return True  # fallback: 통과
    last = df5.iloc[-1]
    op = float(last['Open']); cl = float(last['Close']); lo = float(last['Low'])
    return (cl > op) and (lo <= zone_high) and (cl >= zone_low)


# ────────────────────────────────────────────────────────────
# 버전별 백테스트 엔진
# ────────────────────────────────────────────────────────────
def _run_version(df15: pd.DataFrame, df5: pd.DataFrame | None,
                 market: str, version: str) -> list:
    """
    version: 'V1' | 'V2' | 'V3'
    Returns: list of trade dicts
    """
    if df15 is None or len(df15) < 40:
        return []

    # 버전별 파라미터
    if version == 'V1':
        sl_pct  = 0.005
        tp_pct  = 0.010
        need_quality = False
        need_5m      = False
    elif version == 'V2':
        sl_pct  = 0.010
        tp_pct  = 0.030 if market == 'CRYPTO' else 0.020
        need_quality = True
        need_5m      = False
    else:  # V3
        sl_pct  = 0.010
        tp_pct  = 0.030 if market == 'CRYPTO' else 0.020
        need_quality = True
        need_5m      = True if market in ('KR', 'CRYPTO') else False

    fee      = FEE.get(market, 0.001)
    zones    = _detect_fvg(df15) + _detect_ob(df15)
    trades   = []
    in_trade = False

    for i in range(30, len(df15)):
        if in_trade:
            hi = float(df15['High'].iloc[i])
            lo = float(df15['Low'].iloc[i])
            cl = float(df15['Close'].iloc[i])
            hold = i - entry_i

            if hi >= tp_price:
                pnl_g = tp_pct
                trades.append({'result':'WIN','reason':'TP',
                               'pnl_gross':pnl_g,'pnl_net':pnl_g - fee,
                               'hold_bars':hold,'zone_type':ez})
                in_trade = False
            elif lo <= sl_price:
                pnl_g = -sl_pct
                trades.append({'result':'LOSS','reason':'SL',
                               'pnl_gross':pnl_g,'pnl_net':pnl_g - fee,
                               'hold_bars':hold,'zone_type':ez})
                in_trade = False
            elif hold >= 96:  # 24시간 최대 보유 (96 × 15m)
                pnl_g = (cl - entry_px) / entry_px
                trades.append({'result':'WIN' if pnl_g > 0 else 'LOSS',
                               'reason':'MAX_HOLD',
                               'pnl_gross':pnl_g,'pnl_net':pnl_g - fee,
                               'hold_bars':hold,'zone_type':ez})
                in_trade = False
            continue

        # ── 진입 조건 탐색 ──────────────────────────────────────
        sub = df15.iloc[:i+1]
        bar = sub.iloc[-1]
        op  = float(bar['Open'])
        cl  = float(bar['Close'])
        lo  = float(bar['Low'])
        hi  = float(bar['High'])

        for z in zones:
            if z['formed_i'] >= i or z['expire_i'] < i:
                continue
            zh = z['zone_high']; zl = z['zone_low']
            if not (lo <= zh and cl >= zl):
                continue

            entry = cl

            # V2/V3: 1순위 필터 (Vol_Spike + Body_In_Zone)
            if need_quality:
                vs, biz = _quality_flags(sub, entry, zl)
                if not (vs and biz):
                    continue
                # 2순위: zone_mid
                if not _zone_mid_ok(sub, zl, zh):
                    continue

            # V3: 5m 확인 캔들
            if need_5m and df5 is not None:
                if not _5m_confirm(df5, zl, zh):
                    continue

            # 진입 확정
            in_trade  = True
            entry_i   = i
            entry_px  = entry
            tp_price  = entry * (1 + tp_pct)
            sl_price  = entry * (1 - sl_pct)
            ez        = z['type']
            break

    return trades


# ────────────────────────────────────────────────────────────
# 성과 요약
# ────────────────────────────────────────────────────────────
def _summary(trades: list) -> dict:
    if not trades:
        return {'count':0,'win_rate':0,'gross_pnl':0,'net_pnl':0,
                'ev':0,'mdd':0,'avg_hold_h':0}
    df  = pd.DataFrame(trades)
    n   = len(df)
    wr  = len(df[df['result']=='WIN']) / n * 100
    gp  = df['pnl_gross'].sum() * 100
    np_ = df['pnl_net'].sum() * 100
    ev  = np_ / n
    cum = df['pnl_net'].cumsum()
    mdd = ((cum - cum.cummax()) / (1 + cum.cummax())).min() * 100
    avg_h = df['hold_bars'].mean() * 15 / 60   # bars → hours
    return {'count':n,'win_rate':round(wr,1),'gross_pnl':round(gp,2),
            'net_pnl':round(np_,2),'ev':round(ev,3),
            'mdd':round(mdd,2),'avg_hold_h':round(avg_h,1)}


# ────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print("  단타 버전별 수익률 비교 (60일 15분봉 백테스트, 2026-04-28)")
    print("  V1: 기존(SL0.5%/TP1%) | V2: 신규SL/TP+품질필터 | V3: V2+5m확인")
    print("=" * 78)

    results = []

    for code, (name, yf_tk, market) in UNIVERSE_15M.items():
        print(f"  다운로드: {name}({code}) ...", end=' ', flush=True)
        df15 = _load_15m(yf_tk)
        df5  = _load_5m(yf_tk) if market in ('KR','CRYPTO') else None
        if df15 is None or len(df15) < 40:
            print("데이터 없음")
            continue
        print(f"{len(df15)}봉")

        for ver in ('V1','V2','V3'):
            trades = _run_version(df15, df5, market, ver)
            s = _summary(trades)
            s['version'] = ver
            s['code']    = code
            s['name']    = name
            s['market']  = market
            results.append(s)

    # ── 출력: 종목별 ────────────────────────────────────────────
    print("\n" + "─" * 78)
    print(f"  {'종목':<12} {'시장':<7} {'버전':<5} {'건수':>4} {'승률':>6} "
          f"{'수수료전':>8} {'수수료후':>8} {'EV':>7} {'MDD':>7} {'평균보유':>7}")
    print("─" * 78)

    df_all = pd.DataFrame(results)
    for code, grp in df_all.groupby('code', sort=False):
        name   = grp['name'].iloc[0]
        market = grp['market'].iloc[0]
        for _, row in grp.iterrows():
            ver_label = {'V1':'[기존]','V2':'[중간]','V3':'[최종]'}[row['version']]
            print(f"  {name:<10} {market:<7} {ver_label:<7} {int(row['count']):>4}건 "
                  f"{row['win_rate']:>5.1f}% {row['gross_pnl']:>+8.2f}% "
                  f"{row['net_pnl']:>+8.2f}% {row['ev']:>+7.3f}% "
                  f"{row['mdd']:>+7.2f}% {row['avg_hold_h']:>5.1f}h")
        print()

    # ── 전체 합산 ────────────────────────────────────────────────
    print("=" * 78)
    print("  [전체 합산]")
    print("─" * 78)
    print(f"  {'버전':<9} {'건수':>5} {'승률':>6} {'수수료전':>9} {'수수료후':>9} "
          f"{'EV/건':>8} {'MDD':>8}")
    print("─" * 78)

    for ver in ('V1','V2','V3'):
        sub = df_all[df_all['version'] == ver]
        n   = int(sub['count'].sum())
        if n == 0: continue
        # 합산은 건수 가중
        wr_w  = (sub['win_rate']  * sub['count']).sum() / n
        gp    = sub['gross_pnl'].sum()
        np_   = sub['net_pnl'].sum()
        ev    = np_ / n
        mdd_w = sub['mdd'].min()
        ver_label = {'V1':'[기존]','V2':'[중간]','V3':'[최종]'}[ver]
        print(f"  {ver_label:<9} {n:>5}건 {wr_w:>5.1f}% {gp:>+9.2f}% "
              f"{np_:>+9.2f}% {ev:>+8.3f}% {mdd_w:>+8.2f}%")

    # ── 시장별 합산 ──────────────────────────────────────────────
    print("\n  [시장별 합산]")
    print("─" * 78)
    for mkt in ('KR','US','CRYPTO'):
        sub_m = df_all[df_all['market'] == mkt]
        if sub_m.empty: continue
        print(f"  [{mkt}]")
        for ver in ('V1','V2','V3'):
            sub = sub_m[sub_m['version'] == ver]
            n   = int(sub['count'].sum())
            if n == 0: continue
            wr_w = (sub['win_rate'] * sub['count']).sum() / n
            np_  = sub['net_pnl'].sum()
            ev   = np_ / n
            ver_label = {'V1':'[기존]','V2':'[중간]','V3':'[최종]'}[ver]
            print(f"    {ver_label:<9} {n:>4}건  WR {wr_w:5.1f}%  "
                  f"수수료후 {np_:+8.2f}%  EV {ev:+.3f}%/건")
        print()

    # ── 결론 ────────────────────────────────────────────────────
    print("=" * 78)
    print("  [수수료 분석 요약]")
    print(f"  KR  수수료 0.23%:  TP 1%→순수익 0.77%  |  TP 2%→순수익 1.77%")
    print(f"  US  수수료 0.50%:  TP 1%→순수익 0.50%  |  TP 2%→순수익 1.50%")
    print(f"  CRYPTO 수수료 0.10%: TP 1%→순수익 0.90%  |  TP 3%→순수익 2.90%")
    print("=" * 78)

    # ── CSV + Markdown 저장 ─────────────────────────────────────
    df_all.to_csv('logs/version_compare_bt.csv', index=False, encoding='utf-8-sig')

    # Markdown 문서 생성
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    md_lines = [
        f"# 단타 버전별 수익률 비교 — {now_str}",
        "",
        "## 버전 정의",
        "| 버전 | SL | TP | 품질필터 | 5m확인 |",
        "|------|----|----|---------|--------|",
        "| V1 기존 | 0.5% | 1.0% (전 시장 동일) | 없음 | 없음 |",
        "| V2 중간 | 1.0% | KR·US 2% / CRYPTO 3% | Vol_Spike+Body_In_Zone+zone_mid | 없음 |",
        "| V3 최종 | 1.0% | KR·US 2% / CRYPTO 3% | Vol_Spike+Body_In_Zone+zone_mid | KR·CRYPTO ON |",
        "",
        "## 시장별 전략 방향",
        "| 시장 | 수수료 | 전략 | TP 목표 | 순수익 |",
        "|------|--------|------|---------|--------|",
        "| CRYPTO | 0.10% | 단타 FVG+OB+5m | 3% | 2.90% |",
        "| KR | 0.23% | 단타→스윙 전환 검토 | 2%(단타)/6%(스윙) | 1.77%/5.77% |",
        "| US | 0.50% | 단타→스윙 전환 검토 | 2%(단타)/6%(스윙) | 1.50%/5.50% |",
        "",
        "## 전체 합산 결과",
        "| 버전 | 건수 | 승률 | 수수료전 | 수수료후 | EV/건 | MDD |",
        "|------|------|------|---------|---------|-------|-----|",
    ]

    for ver in ('V1','V2','V3'):
        sub = df_all[df_all['version'] == ver]
        n   = int(sub['count'].sum())
        if n == 0: continue
        wr_w = (sub['win_rate'] * sub['count']).sum() / n
        gp   = sub['gross_pnl'].sum()
        np_  = sub['net_pnl'].sum()
        ev   = np_ / n
        mdd  = sub['mdd'].min()
        ver_label = {'V1':'V1 기존','V2':'V2 중간','V3':'V3 최종'}[ver]
        md_lines.append(
            f"| {ver_label} | {n}건 | {wr_w:.1f}% | {gp:+.2f}% | "
            f"{np_:+.2f}% | {ev:+.3f}% | {mdd:+.2f}% |"
        )

    md_lines += [
        "",
        "## 스윙 백테스트 요약 (별도: swing_bt.py)",
        "| 전략 | 건수 | 승률(KR) | 수수료후(KR) | 승률(US) | 수수료후(US) |",
        "|------|------|---------|------------|---------|------------|",
        "| FVG+OB | 257 | 49.0% | +295.48% | 244 | 39.8% / +15.87% |",
        "| FVG+OB+DBB | 35 | **60.0%** | +75.95% | 70 | 40.0% / +7.00% |",
        "",
        "## 결론 및 제안",
        "1. **CRYPTO**: V3(5m확인+TP3%) 적용 — 수수료 0.10%로 단타 최적",
        "2. **KR**: DBB 스윙 전략(WR 60%, TP 6%) 병행 검토. 단타는 V3 유지",
        "3. **US**: 수수료 0.50%로 단타 순수익 박함 → 스윙 FVG+OB(TP6%) 전환 추천",
        "4. **다음 액션**: 충분한 포워드 데이터(1~2주) 후 V2/V3 성과 실제 비교",
        "",
        "---",
        f"*작성: Warren Trading Bot — {now_str}*",
    ]

    md_path = 'logs/journal/2026-04-28-version-compare.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    print(f"\n  결과 저장:")
    print(f"    CSV : logs/version_compare_bt.csv")
    print(f"    보고서: {md_path}")
    print("=" * 78)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
