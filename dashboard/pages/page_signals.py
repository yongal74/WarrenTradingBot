# -*- coding: utf-8 -*-
"""FVG+OB 신호 스캐너 — 실시간 신호 + 포워드테스트 현황"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

LOG_DIR = Path(__file__).parent.parent.parent / 'logs'


def _signal_log() -> pd.DataFrame:
    p = LOG_DIR / 'forward_signals.csv'
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, encoding='utf-8-sig')
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


def render():
    st.markdown("### FVG+OB 신호 스캐너")

    # ── 컨트롤 바 ─────────────────────────────────────────────
    ctrl = st.columns([2, 1, 1, 1])
    with ctrl[0]:
        scan_btn = st.button("전종목 즉시 스캔 (KR5+US5+CRYPTO4)", type="primary",
                             use_container_width=True)
    with ctrl[1]:
        auto_save = st.checkbox("결과 자동 저장", value=True)
    with ctrl[2]:
        notify = st.checkbox("텔레그램 알림", value=False)
    with ctrl[3]:
        st.markdown(f"<div style='font-size:11px;color:#787b86;padding-top:8px;'>"
                    f"마지막 스캔: {datetime.now().strftime('%H:%M:%S')}</div>",
                    unsafe_allow_html=True)

    # ── 스캔 실행 ─────────────────────────────────────────────
    if scan_btn:
        with st.spinner("KR5 + US5 스캔 중... (약 20초 소요)"):
            try:
                import io, contextlib
                from core.fvg_ob_tester import scan_all
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    signals = scan_all()
            except Exception as e:
                st.error(f"스캔 오류: {e}")
                signals = []

        if signals:
            st.success(f"신호 {len(signals)}건 발생 [{datetime.now().strftime('%H:%M:%S')}]")

            # 신호 카드 그리드
            for i in range(0, len(signals), 2):
                cols = st.columns(2)
                for j, s in enumerate(signals[i:i+2]):
                    mkt   = s.get('market', '')
                    is_kr = mkt == 'KR'
                    fmt   = ',.0f' if is_kr else '.4f'
                    stype = s.get('type', '')
                    color = '#26a69a' if stype == 'FVG' else '#42a5f5'
                    price = s.get('price', 0)
                    entry = s.get('entry', 0)
                    tp    = s.get('tp_pct', 0)
                    sl    = s.get('sl_pct', 0)

                    cols[j].markdown(f"""
                    <div style='background:#1e222d;border:1px solid {color};border-radius:6px;
                    padding:10px 14px;'>
                      <div style='display:flex;justify-content:space-between;align-items:center;'>
                        <span style='font-size:14px;font-weight:700;color:#d1d4dc;'>
                          {s.get('name','')} <span style='color:#787b86;font-size:12px;'>({s.get('ticker','')})</span>
                        </span>
                        <span style='background:rgba({",".join(["38,166,154" if stype=="FVG" else "33,150,243"])},0.2);
                        color:{color};padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;'>
                          {stype}
                        </span>
                      </div>
                      <div style='margin-top:8px;display:grid;grid-template-columns:repeat(4,1fr);gap:4px;'>
                        <div><div style='font-size:10px;color:#787b86;'>현재가</div>
                             <div style='font-size:13px;font-weight:600;color:#d1d4dc;'>{price:{fmt}}</div></div>
                        <div><div style='font-size:10px;color:#787b86;'>진입</div>
                             <div style='font-size:13px;font-weight:600;color:#d1d4dc;'>{entry:{fmt}}</div></div>
                        <div><div style='font-size:10px;color:#787b86;'>TP</div>
                             <div style='font-size:13px;font-weight:600;color:#26a69a;'>+{tp:.2f}%</div></div>
                        <div><div style='font-size:10px;color:#787b86;'>SL</div>
                             <div style='font-size:13px;font-weight:600;color:#ef5350;'>{sl:.2f}%</div></div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            # CSV 저장
            if auto_save:
                sig_df_new = pd.DataFrame(signals)
                sig_df_new['date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                p = LOG_DIR / 'forward_signals.csv'
                if p.exists():
                    existing = pd.read_csv(p, encoding='utf-8-sig')
                    sig_df_new = pd.concat([existing, sig_df_new], ignore_index=True)
                sig_df_new.to_csv(p, index=False, encoding='utf-8-sig')
                st.caption("신호 자동 저장 완료")

            # 텔레그램 알림
            if notify:
                try:
                    from agents.telegram_agent import TelegramAgent
                    tg = TelegramAgent()
                    for s in signals:
                        tg.send(f"[Warren] {s['type']} 신호: {s['name']} | TP +{s['tp_pct']:.2f}% | SL {s['sl_pct']:.2f}%")
                    st.caption("텔레그램 알림 전송 완료")
                except Exception as e:
                    st.caption(f"텔레그램 오류: {e}")
        else:
            st.info("현재 신호 없음 — 다음 15분봉 대기")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── 누적 신호 로그 분석 ────────────────────────────────────
    log_df = _signal_log()

    # KPI 요약
    k1, k2, k3, k4, k5, k6 = st.columns(6)

    def _kpi_sm(col, label, val, color='#d1d4dc'):
        col.markdown(f"""<div class='kpi-card'>
        <div class='kpi-val' style='color:{color};font-size:16px;'>{val}</div>
        <div class='kpi-label'>{label}</div></div>""", unsafe_allow_html=True)

    if not log_df.empty:
        total_sig = len(log_df)
        kr_cnt  = len(log_df[log_df['market']=='KR'])  if 'market' in log_df.columns else 0
        us_cnt  = len(log_df[log_df['market']=='US'])  if 'market' in log_df.columns else 0
        cr_cnt  = len(log_df[log_df['market']=='CRYPTO']) if 'market' in log_df.columns else 0
        fvg_cnt = len(log_df[log_df['type']=='FVG']) if 'type' in log_df.columns else 0
        ob_cnt  = len(log_df[log_df['type']=='OB'])  if 'type' in log_df.columns else 0

        _kpi_sm(k1, "총 신호", total_sig)
        _kpi_sm(k2, "한국주식", kr_cnt, '#26a69a')
        _kpi_sm(k3, "미국주식", us_cnt, '#42a5f5')
        _kpi_sm(k4, "암호화폐", cr_cnt, '#ffb74d')
        _kpi_sm(k5, "FVG", fvg_cnt, '#26a69a')
        _kpi_sm(k6, "OB",  ob_cnt,  '#42a5f5')
    else:
        for col, label in zip([k1,k2,k3,k4,k5,k6], ['총 신호','한국','미국','코인','FVG','OB']):
            _kpi_sm(col, label, 0)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── 탭: 로그 테이블 / 차트 / 포워드테스트 현황 ────────────
    tab1, tab2, tab3 = st.tabs(["신호 로그", "시계열 차트", "포워드테스트 현황"])

    with tab1:
        if not log_df.empty:
            show_cols = [c for c in ['date','ticker','name','market','type',
                                     'price','entry','tp_pct','sl_pct'] if c in log_df.columns]
            disp = log_df[show_cols].iloc[::-1].reset_index(drop=True)
            st.dataframe(disp, width='stretch', hide_index=True, height=400)

            dl = log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("CSV 다운로드", dl, "forward_signals.csv", "text/csv")
        else:
            st.info("신호 로그 없음 — 스캔 후 자동 저장됩니다")

    with tab2:
        if not log_df.empty and 'date' in log_df.columns:
            daily = log_df.copy()
            daily['day'] = daily['date'].dt.date
            cnt_by_day = daily.groupby('day').size().reset_index(name='count')

            fig = go.Figure()
            if 'type' in log_df.columns:
                for stype, color in [('FVG','#26a69a'),('OB','#42a5f5')]:
                    sub = daily[daily['type']==stype].groupby('day').size().reset_index(name='count')
                    fig.add_trace(go.Bar(x=sub['day'], y=sub['count'],
                                         name=stype, marker_color=color))
            else:
                fig.add_trace(go.Bar(x=cnt_by_day['day'], y=cnt_by_day['count'],
                                     marker_color='#26a69a', name='신호'))

            fig.update_layout(
                height=300, barmode='stack',
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#131722',
                font=dict(color='#787b86', size=11),
                margin=dict(t=4, b=4, l=4, r=4),
                xaxis=dict(gridcolor='#1e222d', color='#787b86', tickfont=dict(size=10)),
                yaxis=dict(gridcolor='#1e222d', color='#787b86', tickfont=dict(size=10)),
                legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=10)),
            )
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

            # 시장별 파이차트
            if 'market' in log_df.columns:
                mkt_cnt = log_df['market'].value_counts()
                fig2 = go.Figure(go.Pie(
                    labels=mkt_cnt.index, values=mkt_cnt.values, hole=0.5,
                    marker_colors=['#26a69a','#42a5f5','#ffb74d'],
                    textfont=dict(size=11),
                ))
                fig2.update_layout(
                    height=220, paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#787b86', size=11),
                    margin=dict(t=4, b=4, l=4, r=4),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=10)),
                )
                st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
        else:
            st.info("차트를 그릴 데이터 없음")

    with tab3:
        st.markdown("<div class='sec-hdr'>포워드테스트 성과 분석</div>", unsafe_allow_html=True)

        if not log_df.empty and 'tp_pct' in log_df.columns and 'sl_pct' in log_df.columns:
            # 가상 성과: 신호대로 진입했다고 가정
            log_df['rr'] = log_df['tp_pct'].abs() / log_df['sl_pct'].abs().replace(0, 1)
            avg_rr = log_df['rr'].mean()
            avg_tp = log_df['tp_pct'].mean()
            avg_sl = log_df['sl_pct'].mean()

            f1,f2,f3,f4 = st.columns(4)
            _kpi_sm(f1, "평균 R:R", f"{avg_rr:.2f}", '#26a69a')
            _kpi_sm(f2, "평균 TP%", f"+{avg_tp:.2f}%", '#26a69a')
            _kpi_sm(f3, "평균 SL%", f"{avg_sl:.2f}%", '#ef5350')
            _kpi_sm(f4, "총 신호수", len(log_df))

            # TP% 분포
            fig3 = go.Figure()
            fig3.add_trace(go.Histogram(x=log_df['tp_pct'], name='TP%',
                                        marker_color='#26a69a', opacity=0.8,
                                        nbinsx=20))
            fig3.update_layout(
                height=200, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#131722',
                font=dict(color='#787b86', size=11),
                margin=dict(t=4, b=4, l=4, r=4),
                xaxis=dict(gridcolor='#1e222d', color='#787b86', title='TP%'),
                yaxis=dict(gridcolor='#1e222d', color='#787b86', title='건수'),
                showlegend=False,
            )
            st.plotly_chart(fig3, width='stretch', config={'displayModeBar': False})
        else:
            st.info("포워드테스트 데이터 없음 — 스캔 후 자동 표시")
