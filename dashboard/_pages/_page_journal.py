# -*- coding: utf-8 -*-
"""
Warren Trading Journal — 투자일지 페이지
일지 목록 조회 / 작성 / 다운로드
"""
import streamlit as st
from pathlib import Path
from datetime import datetime
import base64

JOURNAL_DIR = Path(__file__).parent.parent.parent / 'logs' / 'journal'
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def _list_journals() -> list[Path]:
    files = sorted(JOURNAL_DIR.glob('*.md'), reverse=True)
    return files


def _read_journal(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _save_journal(filename: str, content: str):
    path = JOURNAL_DIR / filename
    path.write_text(content, encoding='utf-8')
    return path


def _download_link(content: str, filename: str, label: str) -> str:
    b64 = base64.b64encode(content.encode('utf-8')).decode()
    return f'<a href="data:text/markdown;base64,{b64}" download="{filename}">{label}</a>'


def _auto_filename(session: int) -> str:
    date = datetime.now().strftime('%Y-%m-%d')
    return f"{date}-{session:02d}.md"


def _next_session_number() -> int:
    today = datetime.now().strftime('%Y-%m-%d')
    existing = [f for f in JOURNAL_DIR.glob(f'{today}-*.md')]
    return len(existing) + 1


def show():
    st.title("투자일지")
    st.caption("Warren Paper Trading — 일별 투자 기록 및 학습")

    tab1, tab2 = st.tabs(["일지 목록", "새 일지 작성"])

    # ── Tab1: 목록 ────────────────────────────────────────────
    with tab1:
        journals = _list_journals()
        if not journals:
            st.info("작성된 투자일지가 없습니다.")
            return

        # 사이드 목록
        names = [p.name.replace('.md', '') for p in journals]
        selected_name = st.selectbox("일지 선택", names)
        selected_path = JOURNAL_DIR / f"{selected_name}.md"

        if selected_path.exists():
            content = _read_journal(selected_path)

            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(f"**{selected_name}**")
            with col2:
                st.markdown(
                    _download_link(content, f"{selected_name}.md", "다운로드"),
                    unsafe_allow_html=True
                )

            st.divider()
            st.markdown(content)

        st.divider()
        # 전체 다운로드
        if journals:
            all_content = "\n\n---\n\n".join(
                [_read_journal(p) for p in journals]
            )
            st.markdown(
                _download_link(all_content, "Warren_Journal_All.md", "전체 일지 다운로드 (MD)"),
                unsafe_allow_html=True
            )

    # ── Tab2: 새 일지 작성 ────────────────────────────────────
    with tab2:
        st.subheader("새 투자일지 작성")

        session_num = _next_session_number()
        today = datetime.now().strftime('%Y-%m-%d')

        col1, col2 = st.columns(2)
        with col1:
            date_input = st.text_input("날짜", value=today)
        with col2:
            session_input = st.number_input("세션 번호", min_value=1, value=session_num)

        filename = f"{date_input}-{session_input:02d}.md"
        st.caption(f"저장 파일명: {filename}")

        # 템플릿 자동 생성
        template = f"""# Warren Trading Journal — {date_input} #{session_input:02d}
**날짜:** {date_input} | **작성:** {datetime.now().strftime('%H:%M')} KST | **시스템:** V4.5

---

## 포트폴리오 현황

| 시장 | 초기자본 | 가용현금 | 투자중 | 실현손익 | 수익률 |
|------|--------|--------|------|--------|------|
| KR |  |  |  |  |  |
| US |  |  |  |  |  |
| CRYPTO |  |  |  |  |  |
| 합계 |  |  |  |  |  |

총 거래 **X건** | X승 X패 | 승률 **X%**

---

## 오픈 포지션

| 종목 | 진입일 | 진입가 | SL | TP | 포지션 | 현재손익 |
|------|------|------|------|------|------|------|
|  |  |  |  |  |  |  |

---

## [복기 1] 타점 복기 — 어디서 들어갔는가?

> 핵심 질문: **"지금 돌아봐도 그 타점이 맞는가?"**

### 종목명 — 타점 등급: (A/B/C/D/F)
- **진입가**:
- **올바른 전략 기준 타점**:
- **타점 오차**:
- **결과**:
- **교훈**:

---

## [복기 2] 승률 복기 — 왜 이 승률인가?

> 핵심 질문: **"이 패턴이 앞으로도 계속되나? 시스템 문제인가 통계적 노이즈인가?"**

| 전략 | 기대 WR | 실제 WR | 케이스 | 판단 |
|------|--------|--------|------|------|
|  |  |  |  |  |

### 패배 원인 분류
1. **전략 오류**:
2. **타점 오류**:
3. **리스크 관리 오류**:
4. **순수 운**:

### 핵심 판단
>

---

## [복기 3] 전략 복기 — 올바른 전략이 적용됐는가?

> 핵심 질문: **"각 종목이 설계된 전략대로 동작하고 있나?"**

| 종목 | 설계 전략 | 실제 적용 | 일치 |
|------|--------|--------|------|
|  |  |  | ✅/❌ |

### 오늘 전략 변경/수정 사항
| 시각 | 파일 | 변경 내용 |
|------|------|---------|
|  |  |  |

---

## 오늘 모니터링 포인트

1.
2.
3.

## 내일을 위한 규칙

> **규칙 1 (타점)**:
>
> **규칙 2 (승률)**:
>
> **규칙 3 (전략)**:

---
*Warren Trading System V4.5 — Paper Trading*
"""

        content = st.text_area("일지 내용", value=template, height=500)

        col_save, col_preview = st.columns(2)
        with col_save:
            if st.button("저장", type="primary", use_container_width=True):
                _save_journal(filename, content)
                st.success(f"{filename} 저장 완료!")
                st.rerun()

        with col_preview:
            if st.button("미리보기", use_container_width=True):
                with st.expander("미리보기", expanded=True):
                    st.markdown(content)
