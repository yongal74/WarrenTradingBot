# -*- coding: utf-8 -*-
"""FVG+OB 신호 페이지 — KR5 + US5 + CRYPTO 실시간 신호"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'

def render():
    st.markdown("## FVG+OB 실시간 신호 스캐너")
    st.markdown("KR5 + US5 + CRYPTO(ETH/SOL) — 15분봉 FVG+OB 되돌림 신호 감지")

    col_scan, col_info = st.columns([2, 1])

    with col_info:
        st.markdown("""
        <div class='metric-card'>
        <div class='metric-value' style='color:#e3b341;'>FVG+OB</div>
        <div class='metric-label'>전략</div>
        </div>
        <div class='metric-card'>
        <div class='metric-value'>1 : 2</div>
        <div class='metric-label'>R:R 비율</div>
        </div>
        <div class='metric-card'>
        <div class='metric-value'>15분</div>
        <div class='metric-label'>타임프레임</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("**전략 설명**")
        st.markdown("- **FVG**: 3봉 갭 불균형 → 되돌림 진입")
        st.markdown("- **OB**: 충격파 직전 하락봉 → 되돌림 진입")
        st.markdown("- SL: 구간 하단 / TP: SL×2")

    with col_scan:
        if st.button("지금 전종목 스캔", use_container_width=True):
            with st.spinner("KR5 + US5 스캔 중... (약 20초 소요)"):
                try:
                    from core.fvg_ob_tester import scan_all
                    import io, contextlib
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        signals = scan_all()
                except Exception as e:
                    st.error(f"스캔 오류: {e}")
                    return

            st.success(f"스캔 완료 — {len(signals)}건 신호 발생  [{datetime.now().strftime('%H:%M:%S')}]")

            if signals:
                for s in signals:
                    mkt = s.get('market', '')
                    fmt = ',.0f' if mkt == 'KR' else '.2f'
                    color = '#3fb950' if s.get('type') == 'FVG' else '#58a6ff'
                    st.markdown(f"""
                    <div style='background:#1c2128;border:1px solid #30363d;border-radius:8px;
                    padding:14px;margin:8px 0;'>
                    <span style='font-weight:700;font-size:16px;'>{s.get('name')} ({s.get('ticker')})</span>
                    <span style='background:{color};color:white;padding:2px 8px;border-radius:10px;
                    font-size:12px;margin-left:8px;'>{s.get('type')}</span>
                    <span style='color:#8b949e;font-size:12px;margin-left:8px;'>{mkt}</span>
                    <br><br>
                    <span style='color:#8b949e;'>현재가</span> <b>{s.get('price', 0):{fmt}}</b> &nbsp;|&nbsp;
                    <span style='color:#8b949e;'>진입</span> <b>{s.get('entry', 0):{fmt}}</b> &nbsp;|&nbsp;
                    <span style='color:#3fb950;'>TP +{s.get('tp_pct', 0):.2f}%</span> &nbsp;|&nbsp;
                    <span style='color:#f85149;'>SL {s.get('sl_pct', 0):.2f}%</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("현재 신호 없음 — 다음 15분봉 대기")

    st.markdown("---")

    # 누적 신호 로그
    st.markdown("### 누적 신호 로그")
    path = LOG_DIR / 'forward_signals.csv'
    if path.exists():
        df = pd.read_csv(path, encoding='utf-8-sig')
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("총 신호", f"{len(df)}건")
            with c2: st.metric("KR", f"{len(df[df['market']=='KR']) if 'market' in df.columns else 0}건")
            with c3: st.metric("US", f"{len(df[df['market']=='US']) if 'market' in df.columns else 0}건")
            with c4:
                fvg = len(df[df['type']=='FVG']) if 'type' in df.columns else 0
                ob  = len(df[df['type']=='OB']) if 'type' in df.columns else 0
                st.metric("FVG / OB", f"{fvg} / {ob}")

            st.dataframe(df.iloc[::-1].head(50), use_container_width=True, hide_index=True)
            st.download_button("CSV 다운로드", df.to_csv(index=False).encode('utf-8-sig'),
                               "forward_signals.csv", "text/csv")
    else:
        st.info("신호 로그 없음 — 스캔 버튼을 눌러 시작하세요")
