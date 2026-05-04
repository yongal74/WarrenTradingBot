# -*- coding: utf-8 -*-
"""
Warren Strategy V3 백테스트
============================================================
V3 핵심 변경:
  1. KR/US/CRYPTO 전 시장 존기반 SL (0.5~3%), TP = SL*3 (R:R 1:3)
  2. KR/US: 15m 진입 제거 -> 일봉 스윙만
  3. CRYPTO: 4H FVG+OB + Vol_Spike + Body_In_Zone
  4. 쿨다운: 청산 후 4봉(16시간) 동일종목 재진입 차단
  5. 실수수료 반영 (KR 0.23% / US 0.5% / CRYPTO 0.1%)
  6. 실시드 기준 월수익 (KR/US 500만, CRYPTO 2000만/건)
"""
import sys, json, warnings
warnings.filterwarnings("ignore")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import urllib.request
import pandas as pd
import numpy as np

SL_FLOOR    = 0.005
SL_CAP      = 0.030
RR          = 3.0
ZONE_EXPIRE = 30
MAX_HOLD_D  = 15
MAX_HOLD_4H = 90
COOLDOWN_4H = 4
FEE = {"KR": 0.0023, "US": 0.0050, "CRYPTO": 0.0010}
POS_SIZE = {"KR": 5_000_000, "US": 5_000_000, "CRYPTO": 20_000_000}

KR_TICKERS = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "009150.KS": "삼성전기",
    "034020.KS": "두산에너빌리티",
    "008060.KS": "대덕전자",
    "005380.KS": "현대차",
    "000270.KS": "기아",
    "105560.KS": "KB금융",
}
US_TICKERS = {
    "NVDA": "엔비디아",
    "TSLA": "테슬라",
    "AMD":  "AMD",
    "PLTR": "팔란티어",
    "SOXX": "반도체ETF",
    "META": "메타",
    "MSFT": "마이크로소프트",
}
CRYPTO_TICKERS = {
    "BTC-USD": "비트코인",
    "ETH-USD": "이더리움",
    "SOL-USD": "솔라나",
    "XRP-USD": "리플",
    "BNB-USD": "바이낸스코인",
    "ADA-USD": "에이다",
}


def fetch(ticker, interval="1d", range_="5y"):
    imap = {"1d": "1d", "1h": "60m"}
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?interval={imap.get(interval, interval)}&range={range_}")
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        r = data.get("chart", {}).get("result", [])
        if not r:
            return None
        r = r[0]
        ts = r.get("timestamp", [])
        q  = r["indicators"]["quote"][0]
        df = pd.DataFrame({
            "Open":   q["open"],  "High": q["high"],
            "Low":    q["low"],   "Close": q["close"],
            "Volume": q.get("volume", [None] * len(ts)),
        }, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(None))
        return df.dropna()
    except Exception:
        return None


def fetch_4h(ticker):
    df1h = fetch(ticker, "1h", "2y")
    if df1h is None or len(df1h) < 100:
        return None
    return df1h.resample("4h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()


def detect_zones(df, fvg_min=0.003, ob_min=0.005):
    zones = []
    for i in range(2, len(df)):
        hi2 = float(df["High"].iloc[i - 2])
        lo0 = float(df["Low"].iloc[i])
        if lo0 > hi2 and (lo0 - hi2) / hi2 > fvg_min:
            zones.append({"type": "FVG", "fi": i, "zh": lo0, "zl": hi2, "exp": i + ZONE_EXPIRE})
    for i in range(1, len(df) - 2):
        b = df.iloc[i]
        if float(b["Close"]) >= float(b["Open"]):
            continue
        imp = float(df["High"].iloc[i + 1:i + 3].max())
        if (imp - float(b["High"])) / float(b["High"]) > ob_min:
            zones.append({"type": "OB", "fi": i, "zh": float(b["High"]),
                          "zl": float(b["Low"]), "exp": i + ZONE_EXPIRE})
    return zones


def bt_swing(df, market):
    if len(df) < 210:
        return []
    c      = df["Close"]
    ema200 = c.ewm(span=200, adjust=False).mean()
    d      = c.diff()
    g      = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l      = (-d.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rsi    = 100 - 100 / (1 + g / l.replace(0, float("nan")))
    zones  = detect_zones(df)
    fee    = FEE[market]
    trades = []
    i      = 200
    cooldown_until = -1

    while i < len(df) - 1:
        row  = df.iloc[i]
        cl   = float(row["Close"])
        lo   = float(row["Low"])
        e200 = float(ema200.iloc[i])
        r    = float(rsi.iloc[i])

        if pd.isna(e200) or pd.isna(r) or i <= cooldown_until:
            i += 1
            continue
        if cl < e200 * 0.98:
            i += 1
            continue
        if r >= 65:
            i += 1
            continue

        active = [z for z in zones if z["fi"] < i < z["exp"]]
        hit = None
        for z in reversed(active):
            if lo <= z["zh"] and cl >= z["zl"]:
                hit = z
                break
        if not hit:
            i += 1
            continue

        entry  = cl
        raw_sl = (entry - hit["zl"]) / entry if entry > 0 else SL_FLOOR
        sl_pct = max(min(raw_sl, SL_CAP), SL_FLOOR)
        tp_pct = sl_pct * RR
        sl_p   = entry * (1 - sl_pct)
        tp_p   = entry * (1 + tp_pct)

        result = "HOLD"
        exit_p = None
        hold   = MAX_HOLD_D
        for j in range(1, MAX_HOLD_D + 1):
            if i + j >= len(df):
                break
            fut = df.iloc[i + j]
            if float(fut["Low"]) <= sl_p:
                result = "LOSS"; exit_p = sl_p; hold = j; break
            if float(fut["High"]) >= tp_p:
                result = "WIN";  exit_p = tp_p; hold = j; break
        if result == "HOLD":
            exit_p = float(df.iloc[min(i + MAX_HOLD_D, len(df) - 1)]["Close"])
            result = "WIN" if exit_p >= entry else "LOSS"

        gross = (exit_p - entry) / entry
        net   = gross - fee
        trades.append({"result": result, "gross_pct": gross * 100,
                       "net_pct": net * 100, "hold": hold, "type": hit["type"]})
        cooldown_until = i + hold + 1
        i += hold + 1

    return trades


def bt_4h(df, market):
    if len(df) < 50:
        return []
    zones = detect_zones(df, fvg_min=0.0005, ob_min=0.003)
    fee   = FEE[market]
    trades = []
    i      = 20
    cooldown_until = -1

    while i < len(df) - 1:
        row = df.iloc[i]
        cl  = float(row["Close"])
        lo  = float(row["Low"])
        vol = float(row["Volume"]) if row["Volume"] else 0

        if i <= cooldown_until:
            i += 1
            continue

        avg_v = float(df["Volume"].iloc[max(0, i - 20):i].mean()) if i > 20 else 0
        if not (avg_v > 0 and vol > avg_v * 1.5):
            i += 1
            continue

        active = [z for z in zones if z["fi"] < i < z["exp"]]
        hit = None
        for z in reversed(active):
            if lo <= z["zh"] and cl >= z["zl"]:
                mid = z["zl"] + (z["zh"] - z["zl"]) * 0.5
                if cl >= mid:
                    hit = z
                    break
        if not hit:
            i += 1
            continue

        entry  = cl
        raw_sl = (entry - hit["zl"]) / entry if entry > 0 else SL_FLOOR
        sl_pct = max(min(raw_sl, SL_CAP), SL_FLOOR)
        tp_pct = sl_pct * RR
        sl_p   = entry * (1 - sl_pct)
        tp_p   = entry * (1 + tp_pct)

        result = "HOLD"
        exit_p = None
        hold   = MAX_HOLD_4H
        for j in range(1, MAX_HOLD_4H + 1):
            if i + j >= len(df):
                break
            fut = df.iloc[i + j]
            if float(fut["Low"]) <= sl_p:
                result = "LOSS"; exit_p = sl_p; hold = j; break
            if float(fut["High"]) >= tp_p:
                result = "WIN";  exit_p = tp_p; hold = j; break
        if result == "HOLD":
            exit_p = float(df.iloc[min(i + MAX_HOLD_4H, len(df) - 1)]["Close"])
            result = "WIN" if exit_p >= entry else "LOSS"

        gross = (exit_p - entry) / entry
        net   = gross - fee
        trades.append({"result": result, "gross_pct": gross * 100,
                       "net_pct": net * 100, "hold": hold, "type": hit["type"]})
        cooldown_until = i + hold + COOLDOWN_4H
        i += hold + 1

    return trades


def summarize(trades, market, name, tf):
    if not trades:
        return None
    n    = len(trades)
    wins = sum(1 for t in trades if t["result"] == "WIN")
    wr   = wins / n * 100
    ev_g = np.mean([t["gross_pct"] for t in trades])
    ev_n = np.mean([t["net_pct"]   for t in trades])
    months    = 60 if tf == "daily" else 24
    mth_n     = n / months
    mth_r_pct = mth_n * ev_n
    mth_won   = POS_SIZE[market] * mth_r_pct / 100
    return {
        "name": name, "market": market, "tf": tf,
        "n": n, "wr": wr, "ev_gross": ev_g, "ev_net": ev_n,
        "mth_n": mth_n, "mth_r_pct": mth_r_pct, "mth_won": mth_won,
    }


def main():
    print("=" * 72)
    print("  Warren Strategy V3 백테스트")
    print("  존기반 SL(0.5~3%) x R:R 1:3 | KR/US 일봉스윙 | CRYPTO 4H")
    print("  수수료: KR 0.23% / US 0.50% / CRYPTO 0.10%")
    print("  실시드: KR/US 500만원/건 | CRYPTO 2,000만원/건")
    print("=" * 72)

    all_results = []

    print("\n[KR 일봉 스윙]")
    for ticker, name in KR_TICKERS.items():
        print(f"  {name}...", end="", flush=True)
        df = fetch(ticker, "1d", "5y")
        if df is None or len(df) < 220:
            print(" 데이터부족")
            continue
        trades = bt_swing(df, "KR")
        r = summarize(trades, "KR", name, "daily")
        if r:
            flag = "★" if r["wr"] >= 50 and r["ev_net"] > 0 else " "
            print(f" {flag}{r['n']}건 WR={r['wr']:.0f}% gross={r['ev_gross']:+.2f}% net={r['ev_net']:+.2f}% 월{r['mth_won']/10000:+.1f}만원")
            all_results.append(r)
        else:
            print(" 신호없음")

    print("\n[US 일봉 스윙]")
    for ticker, name in US_TICKERS.items():
        print(f"  {name}...", end="", flush=True)
        df = fetch(ticker, "1d", "5y")
        if df is None or len(df) < 220:
            print(" 데이터부족")
            continue
        trades = bt_swing(df, "US")
        r = summarize(trades, "US", name, "daily")
        if r:
            flag = "★" if r["wr"] >= 50 and r["ev_net"] > 0 else " "
            print(f" {flag}{r['n']}건 WR={r['wr']:.0f}% gross={r['ev_gross']:+.2f}% net={r['ev_net']:+.2f}% 월{r['mth_won']/10000:+.1f}만원")
            all_results.append(r)
        else:
            print(" 신호없음")

    print("\n[CRYPTO 4H]")
    for ticker, name in CRYPTO_TICKERS.items():
        print(f"  {name}...", end="", flush=True)
        df = fetch_4h(ticker)
        if df is None or len(df) < 50:
            print(" 데이터부족")
            continue
        trades = bt_4h(df, "CRYPTO")
        r = summarize(trades, "CRYPTO", name, "4H")
        if r:
            flag = "★" if r["wr"] >= 50 and r["ev_net"] > 0 else " "
            print(f" {flag}{r['n']}건 WR={r['wr']:.0f}% gross={r['ev_gross']:+.2f}% net={r['ev_net']:+.2f}% 월{r['mth_won']/10000:+.1f}만원")
            all_results.append(r)
        else:
            print(" 신호없음")

    if not all_results:
        print("\n결과 없음")
        return

    print("\n" + "=" * 72)
    print("  V3 종목별 요약")
    print("=" * 72)
    print(f"  {'종목':<12} {'시장/TF':<10} {'건수':>5} {'WR':>6} {'EV(net)':>9} {'월수익':>13}  판정")
    print(f"  {'-'*65}")

    viable = []
    for r in sorted(all_results, key=lambda x: -x["mth_won"]):
        ok   = r["wr"] >= 50 and r["ev_net"] > 0
        flag = "★ 편입" if ok else "  제외"
        print(f"  {r['name']:<12} {r['market']}/{r['tf']:<6} {r['n']:>5}건 "
              f"{r['wr']:>5.0f}%  {r['ev_net']:>+7.3f}%  "
              f"{r['mth_won']:>10,.0f}원  {flag}")
        if ok:
            viable.append(r)

    print("\n" + "=" * 72)
    print("  V3 포트폴리오 월수익 (실시드 기준)")
    print("=" * 72)

    seed = {"KR": 50_000_000, "US": 50_000_000, "CRYPTO": 200_000_000}
    total_monthly = 0.0
    by_market = {}
    for r in viable:
        by_market.setdefault(r["market"], []).append(r)
    for mkt, results in sorted(by_market.items()):
        mth = sum(r["mth_won"] for r in results)
        total_monthly += mth
        avg_wr = np.mean([r["wr"] for r in results])
        print(f"  {mkt}: {len(results)}종목 | 평균WR={avg_wr:.0f}% | 월 {mth/10000:,.1f}만원")

    total_seed = float(sum(seed.values()))
    print(f"\n  ★ 전체 월수익: {total_monthly/10000:,.1f}만원")
    print(f"  ★ 시드 대비:   {total_monthly/total_seed*100:.2f}%/월")

    capital  = total_seed
    mth_pct  = total_monthly / capital if capital > 0 else 0
    cum = 0.0
    print(f"\n  [12개월 복리] 초기시드={capital/1e8:.1f}억")
    for m in range(1, 13):
        mo = capital * mth_pct
        capital += mo
        cum += mo
        note = " ★월1000만+" if mo >= 1e7 else (" ★월500만+" if mo >= 5e6 else "")
        if m <= 4 or m % 3 == 0:
            print(f"    {m:2d}월: {capital/1e8:.3f}억  월{mo/10000:,.0f}만원  누적+{cum/10000:,.0f}만원{note}")
    print(f"\n  12개월 후: {capital/1e8:.2f}억 | 누적수익: {cum/10000:,.0f}만원")


if __name__ == "__main__":
    main()
