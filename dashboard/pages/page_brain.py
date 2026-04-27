# -*- coding: utf-8 -*-
"""
Market Brain 페이지 — 5-Pillar 매크로 국면 대시보드
Pillar1: VIX / DXY / US10Y / KRW / Oil → HALT/DEFENSIVE/NORMAL/AGGRESSIVE
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime


# ── Pillar 1 색상 / 설명 매핑 ─────────────────────────────────────
_REGIME_META = {
    'HALT':       {'color': '#f85149', 'bg': 'rgba(248,81,73,.12)',  'label': '전면 차단',   'desc': 'VIX 35+ 위기 수준 — 오늘 거래 없음'},
    'DEFENSIVE':  {'color': '#e3b341', 'bg': 'rgba(227,179,65,.12)', 'label': '방어 모드',   'desc': 'VIX 25+ / 거시 위험 — FVG+OB+품질필터(3점+)'},
    'NORMAL':     {'color': '#58a6ff', 'bg': 'rgba(88,166,255,.10)', 'label': '일반 매매',   'desc': '거시 안정 — 순수 FVG+OB (최고 성과 모드)'},
    'AGGRESSIVE': {'color': '#3fb950', 'bg': 'rgba(63,185,80,.12)',  'label': '적극 매수',   'desc': 'VIX 20 미만 / 모든 지표 긍정 — 적극 진입'},
}

_PILLAR_INFO = [
    ('Pillar 1', '거시 국면',      'VIX / DXY / US10Y / KRW / Oil 5개 지표로 거래 가능 여부 결정'),
    ('Pillar 2', '종목 스크리닝',  'KR5 + US5 + CRYPTO4 — 15종목 고정 유니버스'),
    ('Pillar 3', 'FVG + OB 진입', 'Fair Value Gap & Order Block 되돌림 진입 (핵심 전략)'),
    ('Pillar 4', '품질 필터',      'DEFENSIVE 국면에서만 활성 — 7점 중 3점 이상 (RSI/Volume/EMA/VWAP 등)'),
    ('Pillar 5', '게이트키퍼',     'R:R 1:2 고정 / 일 3회 손절시 차단 / 15:55 강제 청산'),
]


def _indicator_card(label: str, value, unit: str = '',
                    warn: bool = False, danger: bool = False) -> str:
    if danger:
        vc, bc = '#f85149', 'rgba(248,81,73,.1)'
    elif warn:
        vc, bc = '#e3b341', 'rgba(227,179,65,.1)'
    else:
        vc, bc = '#3fb950', 'rgba(63,185,80,.08)'

    val_str = f"{value:.1f}{unit}" if isinstance(value, float) else str(value)
    return f"""
    <div style='background:{bc};border:1px solid {vc}33;border-radius:6px;
    padding:10px 14px;text-align:center;'>
    <div style='font-size:18px;font-weight:700;color:{vc};'>{val_str}</div>
    <div style='font-size:10px;color:#787b86;margin-top:3px;'>{label}</div>
    </div>"""


def render():
    st.markdown("## Market Brain — 5-Pillar 매크로 국면")

    # ── Pillar 1: 매크로 데이터 로드 ──────────────────────────────
    with st.spinner("매크로 지표 조회 중..."):
        try:
            from core.macro_regime import get_regime, min_quality_by_regime
            regime, data = get_regime()
        except Exception as e:
            st.error(f"매크로 데이터 로드 실패: {e}")
            regime, data = 'NORMAL', {}

    meta  = _REGIME_META.get(regime, _REGIME_META['NORMAL'])
    min_q = min_quality_by_regime(regime)

    # ── 국면 배너 ─────────────────────────────────────────────────
    score   = data.get('score', 0)
    reasons = data.get('reasons', [])
    updated = data.get('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))

    st.markdown(f"""
    <div style='background:{meta["bg"]};border:2px solid {meta["color"]};
    border-radius:10px;padding:16px 24px;margin-bottom:16px;
    display:flex;align-items:center;gap:24px;'>
      <div>
        <div style='font-size:28px;font-weight:800;color:{meta["color"]};
        letter-spacing:1px;'>{regime}</div>
        <div style='font-size:12px;color:#d1d4dc;margin-top:4px;'>{meta["label"]} — {meta["desc"]}</div>
        <div style='font-size:11px;color:#787b86;margin-top:4px;'>
          위험 점수: <b style='color:{meta["color"]};'>{score}점</b> &nbsp;|&nbsp;
          품질필터: <b style='color:{meta["color"]};'>{min_q}점 이상</b> &nbsp;|&nbsp;
          갱신: {updated}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 위험 사유 (있을 때만) ──────────────────────────────────────
    if reasons:
        reason_html = " &nbsp;·&nbsp; ".join(
            f"<span style='color:#e3b341;'>⚠ {r}</span>" for r in reasons
        )
        st.markdown(f"<div style='font-size:11px;padding:6px 0;'>{reason_html}</div>",
                    unsafe_allow_html=True)

    st.markdown("---")

    # ── 거시 지표 카드 ────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>MACRO INDICATORS (Pillar 1)</div>",
                unsafe_allow_html=True)

    vix   = data.get('vix')
    dxy   = data.get('dxy')
    dxy5  = data.get('dxy_5d_chg', 0.0)
    t10y  = data.get('t10y')
    krw   = data.get('krw')
    oil   = data.get('oil')

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if vix is not None:
            st.markdown(_indicator_card('VIX (공포지수)', vix,
                danger=(vix > 35), warn=(vix > 25)), unsafe_allow_html=True)
        else:
            st.markdown(_indicator_card('VIX', 'N/A'), unsafe_allow_html=True)

    with c2:
        if dxy is not None:
            st.markdown(_indicator_card(f'DXY (5일 {dxy5:+.1f}%)', dxy,
                danger=(dxy5 > 1.5), warn=(dxy5 > 0.8)), unsafe_allow_html=True)
        else:
            st.markdown(_indicator_card('DXY', 'N/A'), unsafe_allow_html=True)

    with c3:
        if t10y is not None:
            st.markdown(_indicator_card('US10Y (%)', t10y, unit='%',
                danger=(t10y > 4.8), warn=(t10y > 4.2)), unsafe_allow_html=True)
        else:
            st.markdown(_indicator_card('US10Y', 'N/A'), unsafe_allow_html=True)

    with c4:
        if krw is not None:
            st.markdown(_indicator_card('KRW/USD', krw, unit='',
                danger=(krw > 1450), warn=(krw > 1400)), unsafe_allow_html=True)
        else:
            st.markdown(_indicator_card('KRW/USD', 'N/A'), unsafe_allow_html=True)

    with c5:
        if oil is not None:
            st.markdown(_indicator_card('WTI Oil', oil, unit='$',
                warn=(oil > 90)), unsafe_allow_html=True)
        else:
            st.markdown(_indicator_card('WTI Oil', 'N/A'), unsafe_allow_html=True)

    st.markdown("---")

    # ── 5-Pillar 상태 테이블 ──────────────────────────────────────
    st.markdown("<div class='sec-hdr'>5-PILLAR SYSTEM STATUS</div>",
                unsafe_allow_html=True)

    pillar_rows = []
    for name, title, desc in _PILLAR_INFO:
        if name == 'Pillar 1':
            status = '🟥 HALT' if regime == 'HALT' else \
                     ('🟡 DEFENSIVE' if regime == 'DEFENSIVE' else
                      ('🟢 NORMAL' if regime == 'NORMAL' else '🔵 AGGRESSIVE'))
            detail = f"점수={score} | {', '.join(reasons) if reasons else '이상 없음'}"
        elif name == 'Pillar 2':
            status = '🟢 ACTIVE'
            detail = 'KR5 (005930/000660/009150/034020/008060) + US5 + CRYPTO4'
        elif name == 'Pillar 3':
            status = '🟥 BLOCKED' if regime == 'HALT' else '🟢 ACTIVE'
            detail = 'FVG+OB 15분봉 | R:R=1:2 | ZONE_EXPIRE=20봉'
        elif name == 'Pillar 4':
            if regime == 'HALT':
                status = '🟥 BLOCKED'
                detail = '거래 차단됨'
            elif regime == 'DEFENSIVE':
                status = '🟡 ON (3점+)'
                detail = 'RSI<65 / Vol_OK / EMA정배열 / Fresh_Zone / PinBar / VWAP / SwingLow'
            else:
                status = '⚪ OFF'
                detail = f'NORMAL/AGGRESSIVE → 필터 없음 (백테스트 최고 성과: +31.76%)'
        else:  # Pillar 5
            status = '🟢 ACTIVE'
            detail = '일 3손절 차단 / 주간 -10% 시 중단 / 15:55 KR 강제청산'

        pillar_rows.append({
            'Pillar': name,
            '기능': title,
            '상태': status,
            '상세': detail,
        })

    df_pillars = pd.DataFrame(pillar_rows)
    st.dataframe(df_pillars, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 실시간 FVG+OB 신호 (최근 스캔 결과) ──────────────────────
    st.markdown("<div class='sec-hdr'>LATEST FVG+OB SIGNALS (Pillar 3)</div>",
                unsafe_allow_html=True)

    if regime == 'HALT':
        st.error("HALT 모드 — 오늘 거래 없음 (VIX 위기 수준)")
    else:
        sig_log = Path(__file__).parent.parent.parent / 'logs' / 'forward_signals.csv'
        if sig_log.exists():
            try:
                df_sig = pd.read_csv(sig_log, encoding='utf-8-sig')
                if not df_sig.empty:
                    # 최근 24h
                    df_sig['dt'] = pd.to_datetime(df_sig['datetime'], errors='coerce')
                    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=24)
                    df_recent = df_sig[df_sig['dt'] >= cutoff].copy()

                    if df_recent.empty:
                        st.info("최근 24시간 신호 없음 — 마지막 스캔 결과 표시")
                        df_recent = df_sig.tail(15).copy()

                    # 표시 컬럼 선택
                    show_cols = ['datetime', 'name', 'market', 'type',
                                 'price', 'entry', 'tp_pct', 'sl_pct']
                    available = [c for c in show_cols if c in df_recent.columns]
                    df_show = df_recent[available].sort_values('datetime', ascending=False).head(20)
                    df_show.columns = [c.replace('_pct', '(%)') for c in df_show.columns]
                    st.dataframe(df_show, use_container_width=True, hide_index=True)
                    st.caption(f"총 누적 신호: {len(df_sig)}건 | 마지막 스캔: {df_sig['datetime'].iloc[-1]}")
                else:
                    st.info("신호 로그 비어있음")
            except Exception as e:
                st.warning(f"신호 로그 로드 실패: {e}")
        else:
            st.info("신호 로그 없음 — run_forward_daily.py 실행 후 표시됩니다")

    st.markdown("---")

    # ── 국면별 전략 가이드 ────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>REGIME STRATEGY GUIDE</div>",
                unsafe_allow_html=True)

    guide_rows = [
        {'국면': 'HALT',       '진입': '없음',          '필터': '전면 차단',      '목표 R:R': '-',   '비고': 'VIX 35+ 위기 수준'},
        {'국면': 'DEFENSIVE',  '진입': 'FVG+OB',        '필터': '7점 중 3점+',    '목표 R:R': '1:3', '비고': '손실 방어 우선'},
        {'국면': 'NORMAL',     '진입': 'FVG+OB',        '필터': '없음 (최고성과)', '목표 R:R': '1:2', '비고': '+31.76% 백테스트'},
        {'국면': 'AGGRESSIVE', '진입': 'FVG+OB',        '필터': '없음',           '목표 R:R': '1:2', '비고': 'VIX 20 미만 강세장'},
    ]
    df_guide = pd.DataFrame(guide_rows)

    # 현재 국면 강조 표시
    def _style_regime(row):
        if row['국면'] == regime:
            return [f'background-color:{meta["bg"]};color:{meta["color"]};font-weight:700'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_guide.style.apply(_style_regime, axis=1),
        use_container_width=True, hide_index=True
    )

    # ── 새로고침 버튼 ─────────────────────────────────────────────
    st.markdown("")
    if st.button("매크로 재조회", use_container_width=False):
        st.rerun()
