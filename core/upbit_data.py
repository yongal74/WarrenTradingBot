# -*- coding: utf-8 -*-
"""
Upbit 공개 REST API — 일봉 OHLCV 및 현재가.
인증 불필요. CRYPTO 페이퍼 트레이딩에 사용.

market 형식: 'KRW-BTC', 'KRW-ETH', 'KRW-SOL', 'KRW-XRP'
"""
import requests
import pandas as pd
from datetime import datetime

_BASE = 'https://api.upbit.com/v1'
_HEADERS = {'Accept': 'application/json'}


def get_daily_df(market: str, count: int = 200) -> pd.DataFrame | None:
    """
    Upbit 일봉 OHLCV 반환.
    count 최대 200 (API 제한).
    """
    try:
        r = requests.get(
            f'{_BASE}/candles/days',
            params={'market': market, 'count': min(count, 200)},
            headers=_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None

    if not data:
        return None

    records = []
    for c in data:
        try:
            records.append({
                'Date':   c['candle_date_time_kst'][:10],
                'Open':   float(c['opening_price']),
                'High':   float(c['high_price']),
                'Low':    float(c['low_price']),
                'Close':  float(c['trade_price']),
                'Volume': float(c['candle_acc_trade_volume']),
            })
        except (KeyError, TypeError, ValueError):
            continue

    if not records:
        return None

    df = pd.DataFrame(records)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').drop_duplicates('Date').set_index('Date')
    return df[['Open', 'High', 'Low', 'Close', 'Volume']]


def get_current_price(market: str) -> float | None:
    """Upbit 현재가 (최근 체결가) 반환."""
    try:
        r = requests.get(
            f'{_BASE}/ticker',
            params={'markets': market},
            headers=_HEADERS,
            timeout=5,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data:
            return float(data[0]['trade_price'])
    except Exception:
        pass
    return None
