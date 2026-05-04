# -*- coding: utf-8 -*-
"""시스템 문서 페이지 — WARREN_V5.0.md 대시보드 표시"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import json


DOCS_DIR = Path(__file__).parent.parent.parent / 'docs'
PORT_FILE = Path(__file__).parent.parent.parent / 'logs' / 'paper_portfolio.json'


def render():
    st.markdown("## 시스템 문서")

    # ── 버전 정보 KPI ─────────────────────────────────────────────
    try:
        from version import __version__, __release_date__, CHANGELOG
        ver = __version__
        rel = __release_date__
        changes = CHANGELOG.get(ver, [])
    except Exception:
        ver, rel, changes = '5.0.0', '2026-05-01', []

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("현재 버전", f"v{ver}")
    with k2:
        st.metric("릴리즈 날짜", rel)
    with k3:
        # 포트폴리오 메트릭 요약
        try:
            port = json.loads(PORT_FILE.read_text(encoding='utf-8'))
            m = port.get('metrics', {})
            pf = m.get('profit_factor', 0)
            st.metric("Profit Factor", f"{pf:.2f}" if pf and pf != float('inf') else "N/A")
        except Exception:
            st.metric("Profit Factor", "N/A")

    st.markdown("---")

    # ── 메트릭 상세 ───────────────────────────────────────────────
    try:
        port = json.loads(PORT_FILE.read_text(encoding='utf-8'))
        m = port.get('metrics', {})
        if m:
            st.markdown("### 포트폴리오 메트릭 (v5.0)")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                sharpe = m.get('sharpe', 0)
                color = '#26a69a' if sharpe > 0 else '#ef5350'
                st.markdown(f"""<div style='background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:10px 12px;'>
                <div style='font-size:11px;color:#787b86;'>Sharpe Ratio</div>
                <div style='font-size:18px;font-weight:700;color:{color};'>{sharpe:.3f}</div>
                <div style='font-size:10px;color:#787b86;'>&gt;1.0 양호</div>
                </div>""", unsafe_allow_html=True)
            with c2:
                pf = m.get('profit_factor', 0)
                pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
                color2 = '#26a69a' if pf >= 1.0 else '#ef5350'
                st.markdown(f"""<div style='background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:10px 12px;'>
                <div style='font-size:11px;color:#787b86;'>Profit Factor</div>
                <div style='font-size:18px;font-weight:700;color:{color2};'>{pf_str}</div>
                <div style='font-size:10px;color:#787b86;'>&gt;1.5 양호</div>
                </div>""", unsafe_allow_html=True)
            with c3:
                exp = int(m.get('expectancy_krw', 0))
                color3 = '#26a69a' if exp >= 0 else '#ef5350'
                st.markdown(f"""<div style='background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:10px 12px;'>
                <div style='font-size:11px;color:#787b86;'>Expectancy (거래당)</div>
                <div style='font-size:18px;font-weight:700;color:{color3};'>{exp:+,.0f}원</div>
                <div style='font-size:10px;color:#787b86;'>양수이면 장기 흑자</div>
                </div>""", unsafe_allow_html=True)
            with c4:
                avg_w = int(m.get('avg_win_krw', 0))
                avg_l = int(m.get('avg_loss_krw', 0))
                rr = round(avg_w / avg_l, 2) if avg_l > 0 else 0
                st.markdown(f"""<div style='background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:10px 12px;'>
                <div style='font-size:11px;color:#787b86;'>실현 R:R</div>
                <div style='font-size:18px;font-weight:700;color:#d1d4dc;'>1:{rr}</div>
                <div style='font-size:10px;color:#787b86;'>승{avg_w:,.0f} / 패{avg_l:,.0f}원</div>
                </div>""", unsafe_allow_html=True)
            st.markdown("")
    except Exception:
        pass

    # ── 이번 버전 변경사항 ─────────────────────────────────────────
    if changes:
        st.markdown(f"### v{ver} 변경사항")
        for c in changes:
            st.markdown(f"- {c}")
        st.markdown("---")

    # ── MD 문서 선택 & 표시 ───────────────────────────────────────
    md_files = sorted(DOCS_DIR.glob('WARREN_V*.md'), reverse=True) if DOCS_DIR.exists() else []
    if not md_files:
        st.warning("docs/ 폴더에 문서가 없습니다.")
        return

    selected = st.selectbox(
        "문서 선택",
        md_files,
        format_func=lambda p: p.stem,
    )

    try:
        content = selected.read_text(encoding='utf-8')
        st.markdown(content)
    except Exception as e:
        st.error(f"문서 읽기 실패: {e}")
