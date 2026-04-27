# -*- coding: utf-8 -*-
"""Settings 페이지"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from config.settings import (TRADING_MODE, PAPER_CAPITAL, MAX_POSITION_PCT,
                              DAILY_LOSS_LIMIT, WEEKLY_LOSS_LIMIT, MDD_LIMIT, STOP_LOSS_PCT)

def render():
    st.markdown("## ⚙️ Settings")

    st.markdown("### 🔒 현재 설정 (CLAUDE.md 기반)")
    st.info("설정 변경은 `.env` 파일을 수정하세요. 코드 하드코딩 금지.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 거래 설정")
        st.markdown(f"- **모드:** `{TRADING_MODE}`")
        st.markdown(f"- **초기 자금:** `{PAPER_CAPITAL:,.0f}원`")
        st.markdown(f"- **단일 포지션 최대:** `{MAX_POSITION_PCT*100:.0f}%`")

    with c2:
        st.markdown("#### 리스크 한도")
        st.markdown(f"- **일일 손실 한도:** `{DAILY_LOSS_LIMIT*100:.0f}%`")
        st.markdown(f"- **주간 손실 한도:** `{WEEKLY_LOSS_LIMIT*100:.0f}%`")
        st.markdown(f"- **MDD 정지 한도:** `{MDD_LIMIT*100:.0f}%`")
        st.markdown(f"- **개별 손절선:** `{STOP_LOSS_PCT*100:.0f}%`")

    st.markdown("---")
    st.markdown("### 📂 .env 설정 가이드")
    st.code("""# .env 파일 (프로젝트 루트에 생성)
TRADING_MODE=PAPER          # PAPER / LIVE
PAPER_CAPITAL=10000000      # 초기 가상 자금

# 실거래 준비 시 입력
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret

# 텔레그램 알림 (선택)
# 1) @BotFather → /newbot → BOT_TOKEN 발급
# 2) 봇에게 메시지 보낸 뒤 @userinfobot 으로 CHAT_ID 확인
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
""", language='bash')

    st.markdown("### 📲 Telegram 알림 테스트")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("연결 테스트"):
            from agents.telegram_agent import TelegramAgent
            tg = TelegramAgent()
            if tg.enabled:
                ok = tg.test_connection()
                if ok:
                    st.success("Telegram 연결 성공!")
                else:
                    st.error("발송 실패 — 토큰/채팅ID 확인")
            else:
                st.warning(".env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 설정 필요")
    with col_b:
        st.caption("Telegram 알림 수신 내용: 매수/매도 체결, 손절 실행, 서킷브레이커, 일일 리포트")

    st.markdown("---")
    st.markdown("### 📡 TradingView 웹훅 연동 가이드")

    st.info("TradingView에서 신호 발생 시 자동으로 봇이 매매를 실행합니다.")

    with st.expander("연동 방법 (클릭해서 펼치기)", expanded=False):
        st.markdown("""
**Step 1 — 웹훅 서버 실행**
```
run_webhook.bat  (포트 8080)
```

**Step 2 — ngrok으로 외부 노출**
```
run_ngrok.bat
→ Forwarding: https://xxxx.ngrok-free.app
```

**Step 3 — TradingView Pine Script에 Alert 추가**
```pine
// Pine Script Alert 조건 (예: EMA 크로스)
alertcondition(ta.crossover(ema9, ema21), "EMA Buy Signal")
```

**Step 4 — Alert 설정**
- Alert URL: `https://xxxx.ngrok-free.app/webhook`
- Message (JSON):
```json
{
  "ticker":   "NVDA",
  "action":   "BUY",
  "strategy": "S01_EMA9_21",
  "price":    "{{close}}",
  "secret":   "warren2024"
}
```

**지원 종목:** JEPI, JEPQ, QDVO, JFLI, ULTY, QQQI, NVDA, PLTR, QQQ, SOXX, SPY, TSLA, 475080, 498400, 472150
        """)

    st.markdown("### 🚀 실전 투입 체크리스트")
    checks = [
        "Forward Testing 1개월 완료",
        "승률 > 55% 확인",
        "MDD < 15% 유지 확인",
        "샤프 지수 > 1.0 확인",
        "Alpaca API 키 발급 및 .env 입력",
        ".env에서 TRADING_MODE=LIVE 변경",
        "소액(10만원) 테스트 후 본격 운용",
    ]
    for i, c in enumerate(checks):
        st.checkbox(c, key=f"check_{i}")
