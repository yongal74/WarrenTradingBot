# -*- coding: utf-8 -*-
"""
Warren 다전략 종합 백테스트
============================
6가지 전략 × KR 100종목 + US 20종목 + CRYPTO 10종목
전략: VWAP돌파 / SuperTrend / MACD / 갭앤고 / BB반등 / 모멘텀
타임프레임: KR/US 1H(60일), CRYPTO 4H(2년)
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
import urllib.request
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 파라미터 ──────────────────────────────────────────────────────
RR   = 2.0
FEE  = {'KR': 0.0023, 'US': 0.0025, 'CRYPTO': 0.001}
ATR_N = 14

# ── KR 100종목 유니버스 ───────────────────────────────────────────
KR_UNIVERSE = {
    # 반도체/전자
    '005930.KS':'삼성전자','000660.KS':'SK하이닉스','009150.KS':'삼성전기',
    '006400.KS':'삼성SDI','003670.KS':'포스코퓨처엠','247540.KS':'에코프로비엠',
    '086520.KS':'에코프로','066970.KS':'엘앤에프','008060.KS':'대덕전자',
    '058470.KS':'리노공업','036930.KS':'주성엔지니어링','240810.KS':'원익IPS',
    '005290.KS':'동진쎄미켐','357780.KS':'솔브레인','014680.KS':'한솔케미칼',
    # 자동차
    '005380.KS':'현대차','000270.KS':'기아','012330.KS':'현대모비스',
    '161390.KS':'한국타이어','073240.KS':'금호타이어',
    # 금융
    '105560.KS':'KB금융','055550.KS':'신한지주','086790.KS':'하나금융',
    '316140.KS':'우리금융','032830.KS':'삼성생명','088350.KS':'한화생명',
    # 에너지/화학
    '051910.KS':'LG화학','096770.KS':'SK이노베이션','010950.KS':'S-Oil',
    '011170.KS':'롯데케미칼','009830.KS':'한화솔루션','005490.KS':'POSCO홀딩스',
    # IT/통신
    '035420.KS':'NAVER','035720.KS':'카카오','017670.KS':'SK텔레콤',
    '030200.KS':'KT','032640.KS':'LG유플러스','323410.KS':'카카오뱅크',
    # 바이오/헬스
    '068270.KS':'셀트리온','207940.KS':'삼성바이오로직스','326030.KS':'SK바이오팜',
    '128940.KS':'한미약품','000100.KS':'유한양행','068760.KS':'셀트리온제약',
    '196170.KS':'알테오젠','302440.KS':'SK바이오사이언스','006280.KS':'녹십자',
    # 건설/중공업
    '034020.KS':'두산에너빌','000720.KS':'현대건설','028050.KS':'삼성엔지니어링',
    '006360.KS':'GS건설','009540.KS':'한국조선해양','329180.KS':'현대중공업',
    '010140.KS':'삼성중공업','241560.KS':'두산밥캣',
    # 방산/항공
    '012450.KS':'한화에어로스페이스','079550.KS':'LIG넥스원',
    '272210.KS':'한화시스템','047810.KS':'KAI',
    # 소비재/유통
    '090430.KS':'아모레퍼시픽','051900.KS':'LG생활건강','004370.KS':'농심',
    '271560.KS':'오리온','097950.KS':'CJ제일제당','139480.KS':'이마트',
    '282330.KS':'BGF리테일','007070.KS':'GS리테일','023530.KS':'롯데쇼핑',
    '069960.KS':'현대백화점','021240.KS':'코웨이','008770.KS':'호텔신라',
    '005300.KS':'롯데칠성','000080.KS':'하이트진로',
    # 게임/엔터
    '259960.KS':'크래프톤','036570.KS':'NC소프트','251270.KS':'넷마블',
    '263750.KS':'펄어비스','293490.KS':'카카오게임즈',
    # 지주/기타
    '028260.KS':'삼성물산','003550.KS':'LG','034730.KS':'SK',
    '078930.KS':'GS','000880.KS':'한화','000150.KS':'두산',
    '086280.KS':'현대글로비스','010130.KS':'고려아연',
    # 2차전지 소재
    '066570.KS':'LG전자','402340.KS':'SK스퀘어','120120.KS':'코스모화학',
    # 중소형 유망
    '028300.KS':'에이치엘비','214450.KS':'파마리서치','039200.KS':'오스코텍',
    '185750.KS':'종근당','069620.KS':'대웅제약','170900.KS':'동아에스티',
    '004800.KS':'효성','120110.KS':'코오롱인더','319400.KS':'피에스케이',
}

US_UNIVERSE = {
    'NVDA':'엔비디아','AMD':'AMD','TSLA':'테슬라','PLTR':'팔란티어',
    'SOXX':'반도체ETF','AAPL':'애플','MSFT':'마이크로소프트','GOOGL':'구글',
    'AMZN':'아마존','META':'메타','ARM':'ARM홀딩스','COIN':'코인베이스',
    'MU':'마이크론','AVGO':'브로드컴','QCOM':'퀄컴','INTC':'인텔',
    'SMCI':'슈퍼마이크로','MSTR':'마이크로스트레티지',
    'HOOD':'로빈후드','RBLX':'로블록스',
}

CRYPTO_UNIVERSE = {
    'BTC-USD':'비트코인','ETH-USD':'이더리움','SOL-USD':'솔라나',
    'XRP-USD':'리플','BNB-USD':'BNB','DOGE-USD':'도지코인',
    'ADA-USD':'에이다','AVAX-USD':'아발란체','LINK-USD':'체인링크',
    'DOT-USD':'폴카닷',
}


def fetch(ticker, interval, range_):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
           f'?interval={interval}&range={range_}')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read())
        r    = data.get('chart',{}).get('result',[])
        if not r: return None
        ts = r[0]['timestamp']
        q  = r[0]['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open':   q['open'],'High':q['high'],
            'Low':    q['low'], 'Close':q.get('close',[]),
            'Volume': q.get('volume',[None]*len(ts)),
        }, index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None))
        return df.dropna()
    except:
        return None


def resample_4h(df):
    return df.resample('4h').agg(
        {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    ).dropna()


# ── 인디케이터 계산 ───────────────────────────────────────────────
def atr(df, n=14):
    hi, lo, cl = df['High'], df['Low'], df['Close']
    tr = pd.concat([hi-lo, (hi-cl.shift()).abs(), (lo-cl.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(com=n-1, min_periods=n).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))

def supertrend(df, n=10, mult=3.0):
    hl2   = (df['High'] + df['Low']) / 2
    atr14 = atr(df, n)
    upper = hl2 + mult * atr14
    lower = hl2 - mult * atr14
    trend = pd.Series(1, index=df.index)
    final_upper = upper.copy()
    final_lower = lower.copy()
    for i in range(1, len(df)):
        final_upper.iloc[i] = min(upper.iloc[i], final_upper.iloc[i-1]) if df['Close'].iloc[i-1] <= final_upper.iloc[i-1] else upper.iloc[i]
        final_lower.iloc[i] = max(lower.iloc[i], final_lower.iloc[i-1]) if df['Close'].iloc[i-1] >= final_lower.iloc[i-1] else lower.iloc[i]
        if df['Close'].iloc[i] > final_upper.iloc[i-1]:
            trend.iloc[i] = 1
        elif df['Close'].iloc[i] < final_lower.iloc[i-1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i-1]
    st_line = pd.Series(np.where(trend == 1, final_lower, final_upper), index=df.index)
    return trend, st_line

def vwap_daily(df):
    """일별 VWAP 초기화"""
    df = df.copy()
    df['date'] = df.index.date
    df['tp']   = (df['High'] + df['Low'] + df['Close']) / 3
    df['cumtp'] = df.groupby('date').apply(lambda g: (g['tp']*g['Volume']).cumsum()).values
    df['cumvol'] = df.groupby('date')['Volume'].cumsum().values
    df['vwap']  = df['cumtp'] / df['cumvol'].replace(0, np.nan)
    return df['vwap']


# ── 공통 결과 추적 ───────────────────────────────────────────────
def run_trades(df, signals, sl_arr, tp_arr, fee, max_hold=20):
    """시그널 배열 기반 트레이드 실행"""
    trades = []
    in_trade = False
    for i in range(len(df)):
        if in_trade:
            continue
        if not signals.iloc[i]:
            continue
        entry = float(df['Close'].iloc[i])
        sl    = float(sl_arr.iloc[i])
        tp    = float(tp_arr.iloc[i])
        if sl >= entry or tp <= entry:
            continue
        result = 'HOLD'; exit_p = entry; hold = max_hold
        for j in range(1, max_hold+1):
            if i+j >= len(df): break
            fut = df.iloc[i+j]
            if float(fut['Low']) <= sl:
                result='LOSS'; exit_p=sl; hold=j; break
            if float(fut['High']) >= tp:
                result='WIN';  exit_p=tp; hold=j; break
        if result == 'HOLD':
            exit_p = float(df.iloc[min(i+max_hold,len(df)-1)]['Close'])
            result = 'WIN' if exit_p >= entry else 'LOSS'
        net = (exit_p-entry)/entry - fee
        trades.append({'result':result,'net':net*100,'hold':hold})
        i += hold
    return trades


def score(trades, period_months):
    if not trades or len(trades) < 3:
        return None
    n    = len(trades)
    wins = sum(1 for t in trades if t['result']=='WIN')
    wr   = wins/n*100
    ev   = np.mean([t['net'] for t in trades])
    tot  = sum(t['net'] for t in trades)
    ws   = sum(t['net'] for t in trades if t['result']=='WIN')
    ls   = abs(sum(t['net'] for t in trades if t['result']=='LOSS'))
    pf   = ws/ls if ls>0 else 9.99
    mth_n   = n/period_months
    mth_ret = mth_n*ev
    return {'n':n,'wr':wr,'ev':ev,'tot':tot,'pf':min(pf,9.99),'mth_n':mth_n,'mth_ret':mth_ret}


# ── 6가지 전략 ───────────────────────────────────────────────────
def s1_vwap_breakout(df, fee, max_hold=16):
    """VWAP 돌파: close > VWAP + Vol_Spike"""
    if len(df) < 50: return []
    try:
        vwap  = vwap_daily(df)
        atr14 = atr(df)
        vol20 = df['Volume'].rolling(20).mean()
        sig   = (df['Close'] > vwap) & (df['Close'].shift() <= vwap.shift()) & \
                (df['Volume'] > vol20 * 1.5)
        sl_a  = df['Close'] - 1.5*atr14
        tp_a  = df['Close'] + 1.5*atr14*RR
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


def s2_supertrend(df, fee, max_hold=20):
    """SuperTrend 돌파: 방향 전환 (+1 진입)"""
    if len(df) < 30: return []
    try:
        trend, st_line = supertrend(df)
        sig  = (trend == 1) & (trend.shift() == -1)
        atr14 = atr(df)
        sl_a  = st_line
        tp_a  = df['Close'] + (df['Close'] - sl_a) * RR
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


def s3_macd(df, fee, max_hold=20):
    """MACD 골든크로스"""
    if len(df) < 50: return []
    try:
        cl   = df['Close']
        m12  = cl.ewm(span=12,adjust=False).mean()
        m26  = cl.ewm(span=26,adjust=False).mean()
        macd = m12-m26
        sig9 = macd.ewm(span=9,adjust=False).mean()
        sig  = (macd > sig9) & (macd.shift() <= sig9.shift())
        atr14 = atr(df)
        sl_a  = df['Close'] - 2*atr14
        tp_a  = df['Close'] + 2*atr14*RR
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


def s4_gap_and_go(df, fee, max_hold=8):
    """갭 앤 고: 전봉 대비 1.5% 이상 갭업 + 볼륨 서지"""
    if len(df) < 50: return []
    try:
        gap   = (df['Open'] / df['Close'].shift() - 1)
        vol20 = df['Volume'].rolling(20).mean()
        sig   = (gap > 0.015) & (df['Volume'] > vol20*2.0)
        sl_a  = df['Close'].shift()           # 갭 이전 종가 (갭 메움 = 손절)
        tp_a  = df['Open'] + (df['Open'] - df['Close'].shift()) * RR
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


def s5_bb_reversal(df, fee, max_hold=16):
    """볼린저밴드 하단 반등 + RSI 과매도"""
    if len(df) < 60: return []
    try:
        cl    = df['Close']
        ma20  = cl.rolling(20).mean()
        std20 = cl.rolling(20).std()
        bb_lo = ma20 - 2*std20
        bb_mi = ma20
        rsi14 = rsi(cl)
        sig   = (cl <= bb_lo * 1.01) & (rsi14 < 35) & (cl.shift() > bb_lo.shift())
        atr14 = atr(df)
        sl_a  = cl - 1.5*atr14
        tp_a  = bb_mi    # 중간 밴드 TP
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


def s6_momentum(df, fee, max_hold=20):
    """모멘텀: 20봉 수익률 > 3% + RSI 50~65 진입"""
    if len(df) < 60: return []
    try:
        cl    = df['Close']
        ret20 = cl.pct_change(20) * 100
        rsi14 = rsi(cl)
        sig   = (ret20 > 3) & (rsi14 > 50) & (rsi14 < 65) & \
                (ret20.shift() <= ret20) & (cl > cl.rolling(50).mean())
        atr14 = atr(df)
        sl_a  = cl - 2*atr14
        tp_a  = cl + 2*atr14*RR
        return run_trades(df, sig, sl_a, tp_a, fee, max_hold)
    except:
        return []


STRATEGIES = {
    'S1_VWAP':       s1_vwap_breakout,
    'S2_SuperTrend': s2_supertrend,
    'S3_MACD':       s3_macd,
    'S4_GapGo':      s4_gap_and_go,
    'S5_BBReversal': s5_bb_reversal,
    'S6_Momentum':   s6_momentum,
}


def run_universe(universe, market, interval, range_, period_months, resample=False):
    results = []
    total   = len(universe)
    for idx, (ticker, name) in enumerate(universe.items()):
        print(f'  [{idx+1:3d}/{total}] {name:<14}', end='', flush=True)
        df = fetch(ticker, interval, range_)
        if df is None or len(df) < 50:
            print(' 데이터없음')
            continue
        if resample:
            df = resample_4h(df)
        if len(df) < 30:
            print(' 봉수부족')
            continue

        fee_r = FEE[market]
        row   = {'ticker': ticker, 'name': name, 'market': market, 'bars': len(df)}
        best_ev = -999

        for sname, sfunc in STRATEGIES.items():
            trades = sfunc(df, fee_r)
            sc     = score(trades, period_months)
            if sc:
                row[sname] = sc
                if sc['ev'] > best_ev:
                    best_ev = sc['ev']
                    row['best_strat'] = sname
                    row['best_sc']    = sc

        if 'best_strat' in row:
            bs = row['best_sc']
            flag = '★' if bs['wr'] >= 55 and bs['ev'] > 0 else ('▲' if bs['wr'] >= 45 and bs['ev'] > 0 else ' ')
            print(f' {flag} {row["best_strat"]:<15} WR={bs["wr"]:5.1f}% EV={bs["ev"]:+.3f}% '
                  f'PF={bs["pf"]:.2f} 월={bs["mth_ret"]:+.2f}%')
            results.append(row)
        else:
            print(' 신호없음')

    return results


def print_top(results, market, top_n=15):
    viable = [r for r in results if r['market'] == market and
              r.get('best_sc') and r['best_sc']['ev'] > 0 and r['best_sc']['wr'] >= 45]
    if not viable:
        print(f'  [{market}] 채택 종목 없음')
        return []

    viable.sort(key=lambda x: -x['best_sc']['mth_ret'])
    print(f'\n  [{market}] 상위 {min(top_n, len(viable))}종목 (월수익 기준)')
    print(f'  {"종목":<14} {"전략":<16} {"WR%":<8} {"순EV%":<10} {"PF":<6} {"월수익%"}')
    print('  ' + '-' * 62)
    for r in viable[:top_n]:
        bs = r['best_sc']
        flag = '★' if bs['wr'] >= 55 else '▲'
        print(f'  {flag} {r["name"]:<13} {r["best_strat"]:<16} {bs["wr"]:5.1f}%   '
              f'{bs["ev"]:+.3f}%     {bs["pf"]:4.2f}   {bs["mth_ret"]:+.2f}%/월')
    return viable[:top_n]


def strategy_ranking(results):
    """전략별 평균 성과"""
    print('\n  [전략별 평균 성과 (EV>0 종목 기준)]')
    print(f'  {"전략":<16} {"채택종목수":<10} {"평균WR":<10} {"평균EV":<10} {"평균PF"}')
    print('  ' + '-' * 55)
    for sname in STRATEGIES:
        scs = [r[sname] for r in results if sname in r and r[sname]['ev'] > 0]
        if not scs: continue
        avg_wr  = np.mean([s['wr'] for s in scs])
        avg_ev  = np.mean([s['ev'] for s in scs])
        avg_pf  = np.mean([s['pf'] for s in scs])
        print(f'  {sname:<16} {len(scs):5d}종목     {avg_wr:5.1f}%    {avg_ev:+.3f}%    {avg_pf:.2f}')


def simulate_portfolio(top_kr, top_us, top_crypto):
    SEED = {'KR': 1e7, 'US': 1e7, 'CRYPTO': 5e6}
    groups = {'KR': top_kr[:5], 'US': top_us[:3], 'CRYPTO': top_crypto[:4]}

    print('\n' + '='*70)
    print('  최적 포트폴리오 시뮬레이션')
    print('  시드: KR 1,000만 / US 1,000만 / CRYPTO 500만 = 합계 2,500만원')
    print('='*70)

    total_won = 0.0
    for mkt, grp in groups.items():
        seed = SEED[mkt]
        if not grp:
            print(f'  [{mkt}] 없음')
            continue
        n_g    = len(grp)
        alloc  = seed / n_g
        mth_won = sum(r['best_sc']['mth_ret']/100*alloc for r in grp)
        mth_pct = mth_won/seed*100
        names   = ', '.join(r['name'] for r in grp)
        print(f'  [{mkt}] {n_g}종목: {names}')
        print(f'    시드 {seed/1e4:,.0f}만원 → 월수익 {mth_won/1e4:,.1f}만원 ({mth_pct:.2f}%/월)')
        total_won += mth_won

    total_seed = sum(SEED.values())
    total_pct  = total_won/total_seed*100 if total_seed>0 else 0

    print(f'\n  합계 월수익: {total_won/1e4:,.1f}만원 / {total_pct:.2f}%/월 / APY {total_pct*12:.1f}%')

    if total_pct > 0:
        print('\n  [복리 12개월]')
        cap = total_seed; cum = 0
        for m in range(1, 13):
            mo = cap * total_pct/100
            cap += mo; cum += mo
            if m in (1,3,6,12):
                print(f'    {m:2d}월  {cap/1e4:,.0f}만원  월+{mo/1e4:,.0f}만  누적+{cum/1e4:,.0f}만원')


def main():
    print('='*70)
    print(f'  Warren 다전략 종합 백테스트 [{datetime.now().strftime("%Y-%m-%d %H:%M")}]')
    print('  전략: VWAP돌파/SuperTrend/MACD/갭앤고/BB반등/모멘텀')
    print(f'  KR {len(KR_UNIVERSE)}종목(1H·60일) | US {len(US_UNIVERSE)}종목(1H·60일) | CRYPTO {len(CRYPTO_UNIVERSE)}종목(4H·2년)')
    print('='*70)

    # ── KR ───────────────────────────────────────────────────────
    print(f'\n[1/3] KR {len(KR_UNIVERSE)}종목 분석 중...')
    kr_res = run_universe(KR_UNIVERSE, 'KR', '1h', '60d', 2.0)

    # ── US ───────────────────────────────────────────────────────
    print(f'\n[2/3] US {len(US_UNIVERSE)}종목 분석 중...')
    us_res = run_universe(US_UNIVERSE, 'US', '1h', '60d', 2.0)

    # ── CRYPTO ───────────────────────────────────────────────────
    print(f'\n[3/3] CRYPTO {len(CRYPTO_UNIVERSE)}종목 분석 중 (4H·2년)...')
    cr_res = run_universe(CRYPTO_UNIVERSE, 'CRYPTO', '1h', '2y', 24.0, resample=True)

    all_res = kr_res + us_res + cr_res

    # ── 전략 랭킹 ────────────────────────────────────────────────
    print('\n' + '='*70)
    print('  전략 랭킹')
    print('='*70)
    strategy_ranking(all_res)

    # ── 시장별 TOP 종목 ──────────────────────────────────────────
    print('\n' + '='*70)
    print('  시장별 최적 종목 (전략별 최고 EV 기준)')
    print('='*70)
    top_kr = print_top(kr_res,   'KR',     top_n=15)
    top_us = print_top(us_res,   'US',     top_n=10)
    top_cr = print_top(cr_res,   'CRYPTO', top_n=8)

    # ── 전략별 최강 종목 ─────────────────────────────────────────
    print('\n' + '='*70)
    print('  전략별 최강 종목 Top 5')
    print('='*70)
    for sname in STRATEGIES:
        cands = []
        for r in all_res:
            if sname in r and r[sname]['ev'] > 0 and r[sname]['wr'] >= 40:
                cands.append((r['name'], r['market'], r[sname]))
        cands.sort(key=lambda x: -x[2]['mth_ret'])
        top5 = cands[:5]
        if top5:
            names = ' | '.join(f'{n}({m}) WR={s["wr"]:.0f}% EV={s["ev"]:+.2f}%' for n,m,s in top5)
            print(f'  {sname:<16}: {names}')

    # ── 포트폴리오 시뮬레이션 ────────────────────────────────────
    simulate_portfolio(top_kr, top_us, top_cr)
    print()


if __name__ == '__main__':
    main()
