# -*- coding: utf-8 -*-
"""
KIS (한국투자증권) API 모의투자 트레이더
FVG+OB 신호 수신 -> 모의투자 자동 주문
"""
import os, requests, json, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

# ── 모의투자 엔드포인트 ───────────────────────────────────────
BASE_URL   = 'https://openapivts.koreainvestment.com:29443'
APP_KEY    = os.getenv('KIS_APP_KEY', '').strip()
APP_SECRET = os.getenv('KIS_APP_SECRET', '').strip()
ACCOUNT_NO = os.getenv('KIS_ACCOUNT_NO', '').strip()
ACNT_PROD  = os.getenv('KIS_ACCOUNT_PROD', '01').strip()

# 토큰 캐시
_token_cache = {'token': '', 'expires': 0}

LOG_DIR  = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)
TRADE_LOG = LOG_DIR / 'kis_trades.csv'


def get_token() -> str:
    """액세스 토큰 발급/캐시"""
    now = time.time()
    if _token_cache['token'] and now < _token_cache['expires']:
        return _token_cache['token']

    r = requests.post(
        f'{BASE_URL}/oauth2/tokenP',
        json={'grant_type': 'client_credentials',
              'appkey': APP_KEY, 'appsecret': APP_SECRET},
        timeout=10
    )
    data = r.json()
    if 'access_token' not in data:
        raise RuntimeError(f'토큰 발급 실패: {data}')

    _token_cache['token']   = data['access_token']
    _token_cache['expires'] = now + int(data.get('expires_in', 86400)) - 60
    return _token_cache['token']


def _headers(tr_id: str) -> dict:
    return {
        'authorization': f'Bearer {get_token()}',
        'appkey':        APP_KEY,
        'appsecret':     APP_SECRET,
        'tr_id':         tr_id,
        'Content-Type':  'application/json; charset=utf-8',
    }


def get_balance() -> dict:
    """모의투자 잔고 조회"""
    r = requests.get(
        f'{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance',
        headers=_headers('VTTC8434R'),
        params={
            'CANO': ACCOUNT_NO, 'ACNT_PRDT_CD': ACNT_PROD,
            'AFHR_FLPR_YN': 'N', 'OFL_YN': '', 'INQR_DVSN': '02',
            'UNPR_DVSN': '01', 'FUND_STTL_ICLD_YN': 'N',
            'FNCG_AMT_AUTO_RDPT_YN': 'N', 'PRCS_DVSN': '01',
            'CTX_AREA_FK100': '', 'CTX_AREA_NK100': '',
        },
        timeout=10
    )
    d = r.json()
    if d.get('rt_cd') != '0':
        return {'error': d.get('msg1', '잔고조회 실패')}

    o2 = d.get('output2', [{}])[0]
    positions = []
    for p in d.get('output1', []):
        if int(p.get('hldg_qty', 0)) > 0:
            positions.append({
                'ticker':  p.get('pdno'),
                'name':    p.get('prdt_name'),
                'qty':     int(p.get('hldg_qty', 0)),
                'avg_price': float(p.get('pchs_avg_pric', 0)),
                'cur_price': float(p.get('prpr', 0)),
                'pnl_pct': float(p.get('evlu_pfls_rt', 0)),
            })

    return {
        'cash':       int(o2.get('dnca_tot_amt', 0)),
        'total':      int(o2.get('tot_evlu_amt', 0)),
        'pnl':        int(o2.get('evlu_pfls_smtl_amt', 0)),
        'positions':  positions,
    }


def get_price(ticker: str) -> int:
    """현재가 조회"""
    r = requests.get(
        f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price',
        headers=_headers('FHKST01010100'),
        params={'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': ticker},
        timeout=10
    )
    d = r.json()
    return int(d.get('output', {}).get('stck_prpr', 0))


def buy_order(ticker: str, qty: int, price: int = 0) -> dict:
    """
    모의투자 매수 주문
    price=0 이면 시장가, price>0 이면 지정가
    """
    ord_dvsn = '01' if price == 0 else '00'   # 01=시장가, 00=지정가
    body = {
        'CANO':        ACCOUNT_NO,
        'ACNT_PRDT_CD': ACNT_PROD,
        'PDNO':        ticker,
        'ORD_DVSN':    ord_dvsn,
        'ORD_QTY':     str(qty),
        'ORD_UNPR':    str(price),
    }
    r = requests.post(
        f'{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash',
        headers=_headers('VTTC0802U'),
        json=body, timeout=10
    )
    d = r.json()
    result = {
        'ticker': ticker, 'side': 'BUY', 'qty': qty, 'price': price,
        'success': d.get('rt_cd') == '0',
        'msg': d.get('msg1', ''),
        'order_no': d.get('output', {}).get('ODNO', ''),
        'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _log_trade(result)
    return result


def sell_order(ticker: str, qty: int, price: int = 0) -> dict:
    """모의투자 매도 주문"""
    ord_dvsn = '01' if price == 0 else '00'
    body = {
        'CANO':        ACCOUNT_NO,
        'ACNT_PRDT_CD': ACNT_PROD,
        'PDNO':        ticker,
        'ORD_DVSN':    ord_dvsn,
        'ORD_QTY':     str(qty),
        'ORD_UNPR':    str(price),
    }
    r = requests.post(
        f'{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash',
        headers=_headers('VTTC0801U'),
        json=body, timeout=10
    )
    d = r.json()
    result = {
        'ticker': ticker, 'side': 'SELL', 'qty': qty, 'price': price,
        'success': d.get('rt_cd') == '0',
        'msg': d.get('msg1', ''),
        'order_no': d.get('output', {}).get('ODNO', ''),
        'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _log_trade(result)
    return result


def _log_trade(result: dict):
    """거래 로그 CSV 저장"""
    import csv
    write_header = not TRADE_LOG.exists()
    with open(TRADE_LOG, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=result.keys())
        if write_header: w.writeheader()
        w.writerow(result)


if __name__ == '__main__':
    print('[KIS 모의투자 연결 테스트]')
    bal = get_balance()
    print(f'  예수금: {bal["cash"]:,}원')
    print(f'  총평가: {bal["total"]:,}원')
    print(f'  손익:   {bal["pnl"]:,}원')
    if bal['positions']:
        print('  보유종목:')
        for p in bal['positions']:
            print(f'    {p["name"]}({p["ticker"]}) {p["qty"]}주 {p["pnl_pct"]:+.2f}%')
    else:
        print('  보유종목: 없음')
