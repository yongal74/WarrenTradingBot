# -*- coding: utf-8 -*-
"""통합 데이터 로더 (해외: yfinance / 국내: FinanceDataReader)"""
import warnings; warnings.filterwarnings('ignore')
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from pathlib import Path
from config.settings import DATA_CACHE_DIR, LOOKBACK_DAYS

CACHE_HOURS = 4  # 캐시 유효 시간

def _cache_path(ticker: str) -> Path:
    return DATA_CACHE_DIR / f"{ticker.replace('/', '_')}.csv"

def _is_fresh(path: Path) -> bool:
    if not path.exists(): return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age.total_seconds() < CACHE_HOURS * 3600

def load(ticker: str, market: str = 'US', days: int = None, yf_suffix: str = None) -> pd.DataFrame | None:
    """
    통합 데이터 로드 (캐시 우선)
    ticker: 종목코드
    market: 'US' or 'KR'
    days: 과거 몇 일치 (None이면 LOOKBACK_DAYS)
    """
    cache = _cache_path(ticker)

    # 캐시 히트
    if _is_fresh(cache):
        df = pd.read_csv(cache, index_col=0)
        df.index = pd.to_datetime(df.index, utc=False, errors='coerce')
        df = df[df.index.notna()]
        if len(df) > 50:
            return df

    # 신규 다운로드
    n_days = days or LOOKBACK_DAYS
    start  = (datetime.now() - timedelta(days=n_days + 60)).strftime('%Y-%m-%d')
    end    = datetime.now().strftime('%Y-%m-%d')

    if market == 'CRYPTO':
        # yfinance BTC-USD / ETH-USD 형태
        from config.assets import CRYPTO_ASSETS
        yf_tk = CRYPTO_ASSETS.get(ticker, {}).get('yf', f'{ticker}-USD')
        df = _download_us(yf_tk, start, end)
    elif market == 'US':
        df = _download_us(ticker, start, end)
    else:
        yt = yf_suffix or (ticker + '.KS')
        df = _download_us(yt, start, end)
        if df is None or len(df) < 30:
            df = _download_kr(ticker, start, end)

    if df is not None and len(df) > 10:
        df.to_csv(cache)

    return df

def _download_us(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, start=start, end=end,
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        needed = ['Open','High','Low','Close','Volume']
        for col in needed:
            if col not in df.columns:
                df[col] = 0
        return df[needed].dropna()
    except Exception as e:
        print(f"  [DataLoader] US 다운로드 실패 {ticker}: {e}")
        return None

def _download_kr(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    try:
        df = fdr.DataReader(ticker, start, end)
        if df is None or len(df) < 30: return None
        rename = {'시가':'Open','고가':'High','저가':'Low',
                  '종가':'Close','거래량':'Volume'}
        df = df.rename(columns=rename)
        needed = ['Open','High','Low','Close','Volume']
        for col in needed:
            if col not in df.columns: df[col] = 0
        return df[needed].dropna()
    except Exception as e:
        print(f"  [DataLoader] KR 다운로드 실패 {ticker}: {e}")
        return None

def get_current_price(ticker: str, market: str = 'US') -> float | None:
    """현재가 (최신 종가)"""
    df = load(ticker, market, days=5)
    if df is not None and len(df) > 0:
        return float(df['Close'].iloc[-1])
    return None


def load_intraday(ticker: str, interval: str = '5m') -> pd.DataFrame | None:
    """
    5분봉 / 1분봉 intraday 데이터 로드 (yfinance, 최대 60일)
    interval: '5m' (권장) or '1m' (7일만 가능)
    코인은 BTC → BTC-USD 자동 변환
    """
    # 코인 ticker 변환 (BTC → BTC-USD)
    from config.assets import CRYPTO_ASSETS
    if ticker in CRYPTO_ASSETS:
        yf_ticker = CRYPTO_ASSETS[ticker].get('yf', f'{ticker}-USD')
    else:
        yf_ticker = ticker

    cache_key = f"{ticker.replace('/', '_')}_{interval}"
    cache = DATA_CACHE_DIR / f"{cache_key}.csv"

    if _is_fresh(cache):
        df = pd.read_csv(cache, index_col=0)
        df.index = pd.to_datetime(df.index, utc=False, errors='coerce')
        df = df[df.index.notna()]
        if len(df) > 100:
            return df

    try:
        period = '60d' if interval == '5m' else '7d'
        df = yf.download(yf_ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        needed = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in needed:
            if col not in df.columns:
                df[col] = 0
        df = df[needed].dropna()
        # tz 제거 (naive datetime으로 통일)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        if len(df) > 100:
            df.to_csv(cache)
        return df
    except Exception as e:
        print(f"  [DataLoader] intraday 다운로드 실패 {ticker} {interval}: {e}")
        return None
