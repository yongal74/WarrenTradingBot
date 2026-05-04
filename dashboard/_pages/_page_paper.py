# -*- coding: utf-8 -*-
"""
Paper Trading 대시보드 — V1 / V2 / V3 버전 비교
"""
import json
import csv
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

BASE_DIR = Path(__file__).parent.parent.parent
LOG_DIR  = BASE_DIR / 'logs'

VERSIONS = {
    'v1': 'V1  FVG+OB (버그수정)',
    'v2': 'V2  FVG+DBB (클린)',
    'v3': 'V3  EMA눌림목 (신규)',
}
VERSION_COLOR = {'v1': '#2962ff', 'v2': '#26a69a', 'v3': '#e3b341'}


# ── 데이터 로드 ───────────────────────────────────────────────
@st.cache_data(ttl=60)
def _load_pf(version: str) -> dict:
    f = LOG_DIR / f'{version}_portfolio.json'
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text('utf-8'))
    except Exception:
        return {}


@st.cache_data(ttl=60)
def _load_pos(version: str) -> list:
    f = LOG_DIR / f'{version}_positions.json'
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text('utf-8')).get('positions', [])
    except Exception:
        return []


@st.cache_data(ttl=60)
def _load_trades(version: str) -> pd.DataFrame:
    f = LOG_DIR / f'{version}_trades.csv'
    if not f.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(f, encoding='utf-8-sig')
        df['close_time'] = pd.to_datetime(df['close_time'])
        df['open_time']  = pd.to_datetime(df['open_time'])
        return df
    except Exception:
        return pd.DataFrame()


# ── 통계 계산 ────────────────────────────────────────────────
def _stats(df: pd.DataFrame, pf: dict, positions: list) -> dict:
    initial   = sum(pf.get('initial', {}).values())
    avail     = sum(pf.get('capital', {}).values())
    invested  = sum(float(p.get('size_krw', 0)) for p in positions)
    total_now = avail + invested
    realized  = sum(pf.get('realized', {}).values())
    ret_pct   = (total_now - initial) / initial * 100 if initial else 0

    w = int(pf.get('wins', 0))
    l = int(pf.get('losses', 0))
    total_tr = w + l
    wr = w / total_tr * 100 if total_tr else 0

    if df.empty:
        pf_val, avg_win, avg_loss, expectancy = 0, 0, 0, 0
    else:
        wins_df   = df[df['result'] == 'WIN']['pnl_krw']
        losses_df = df[df['result'] == 'LOSS']['pnl_krw']
        gross_p   = wins_df.sum() if not wins_df.empty else 0
        gross_l   = abs(losses_df.sum()) if not losses_df.empty else 0
        pf_val    = round(gross_p / gross_l, 2) if gross_l else 0
        avg_win   = int(wins_df.mean()) if not wins_df.empty else 0
        avg_loss  = int(losses_df.mean()) if not losses_df.empty else 0
        expectancy = int(df['pnl_krw'].mean()) if not df.empty else 0

    return {
        'initial':    initial,
        'total_now':  total_now,
        'realized':   realized,
        'ret_pct':    round(ret_pct, 2),
        'wins':       w,
        'losses':     l,
        'total_tr':   total_tr,
        'wr':         round(wr, 1),
        'pf':         pf_val,
        'avg_win':    avg_win,
        'avg_loss':   avg_loss,
        'expectancy': expectancy,
        'open_pos':   len(positions),
        'start':      pf.get('start', '-'),
    }


# ── 공통 차트 헬퍼 ────────────────────────────────────────────
_CHART_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='#1e222d',
    font=dict(color='#787b86', size=11),
    margin=dict(t=35, b=10, l=50, r=10),
    xaxis=dict(color='#8b949e', gridcolor='#2a2e39'),
    yaxis=dict(color='#8b949e', gridcolor='#2a2e39'),
)


def _cumulative_pnl_chart(dfs: dict) -> go.Figure:
    """버전별 누적 실현손익 라인 차트."""
    fig = go.Figure()
    for v, df in dfs.items():
        if df.empty:
            continue
        df_s = df.sort_values('close_time')
        df_s['cum_pnl'] = df_s['pnl_krw'].cumsum() / 1e4
        fig.add_trace(go.Scatter(
            x=df_s['close_time'],
            y=df_s['cum_pnl'],
            mode='lines+markers',
            name=VERSIONS[v],
            line=dict(color=VERSION_COLOR[v], width=2),
            marker=dict(size=5),
        ))
    fig.add_hline(y=0, line=dict(color='#363a45', dash='dash'))
    fig.update_layout(
        title=dict(text='누적 실현손익 비교 (만원)',
                   font=dict(color='#d1d4dc', size=13)),
        height=280,
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=11)),
        **_CHART_LAYOUT,
    )
    return fig


def _version_bar_chart(all_stats: dict, metric_key: str,
                        title: str, suffix: str = '') -> go.Figure:
    labels = [VERSIONS[v] for v in VERSIONS]
    values = [all_stats.get(v, {}).get(metric_key, 0) for v in VERSIONS]
    colors = [VERSION_COLOR[v] for v in VERSIONS]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[f"{v}{suffix}" for v in values],
        textposition='outside',
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color='#d1d4dc', size=13)),
        height=260,
        **_CHART_LAYOUT,
    )
    return fig


# ── 단일 버전 상세 렌더 ───────────────────────────────────────
def _render_version_detail(version: str):
    pf       = _load_pf(version)
    positions = _load_pos(version)
    df       = _load_trades(version)

    if not pf:
        st.info(f"`{version}` 미시작 — `run_paper_{version}.bat` 을 실행하세요.")
        return

    s = _stats(df, pf, positions)

    # KPI 행
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("총 자산",
              f"{s['total_now']/1e4:.1f}만",
              f"{s['ret_pct']:+.2f}%")
    c2.metric("실현 손익",
              f"{s['realized']/1e4:+.1f}만")
    c3.metric("거래 / 승률",
              f"{s['total_tr']}건",
              f"{s['wr']:.1f}%  {s['wins']}승 {s['losses']}패")
    c4.metric("Profit Factor", f"{s['pf']:.2f}")
    c5.metric("기대값/trade",  f"{s['expectancy']:+,.0f}원")
    c6.metric("오픈 포지션",   f"{s['open_pos']}개")

    # 오픈 포지션 테이블
    if positions:
        st.markdown("##### 현재 오픈 포지션")
        rows = []
        for p in positions:
            try:
                hold_d = (datetime.now() -
                          datetime.fromisoformat(p['open_time'])).days
            except Exception:
                hold_d = 0
            sl_pct = p.get('sl_pct', 0)
            tp_pct = round((float(p.get('tp', 0)) - float(p.get('entry', 1)))
                           / float(p.get('entry', 1)) * 100, 1)
            rows.append({
                '종목':   p.get('name', p['ticker']),
                '시장':   p.get('market', ''),
                '신호':   p.get('signal_type', ''),
                '진입가': f"{p.get('entry', 0):,.4f}",
                'SL':     f"{p.get('sl', 0):,.4f}  (-{sl_pct:.1f}%)",
                'TP':     f"{p.get('tp', 0):,.4f}  (+{tp_pct:.1f}%)",
                '투자':   f"{p.get('size_krw', 0)/1e4:.0f}만",
                '보유':   f"{hold_d}일",
            })
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True, hide_index=True)

    if df.empty:
        st.info("아직 청산된 거래 없음")
        return

    # 누적 손익 차트
    df_s = df.sort_values('close_time').copy()
    df_s['cum_pnl'] = df_s['pnl_krw'].cumsum() / 1e4
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=df_s['close_time'], y=df_s['cum_pnl'],
        mode='lines+markers',
        line=dict(color=VERSION_COLOR.get(version, '#58a6ff'), width=2),
        fill='tozeroy',
        fillcolor=f"rgba({','.join(str(int(c,16)) for c in [VERSION_COLOR.get(version,'#58a6ff')[1:3],VERSION_COLOR.get(version,'#58a6ff')[3:5],VERSION_COLOR.get(version,'#58a6ff')[5:7]])},0.1)",
        name='누적손익',
    ))
    fig_cum.add_hline(y=0, line=dict(color='#363a45', dash='dash'))
    fig_cum.update_layout(
        title=dict(text=f'[{version.upper()}] 누적 실현손익 (만원)',
                   font=dict(color='#d1d4dc', size=13)),
        height=250, **_CHART_LAYOUT)
    st.plotly_chart(fig_cum, use_container_width=True,
                    config={'displayModeBar': False})

    # 거래 이력 테이블
    st.markdown("##### 거래 이력")
    show_df = df_s[['close_time', 'ticker', 'name', 'market',
                    'signal', 'entry', 'exit', 'pnl_pct',
                    'pnl_krw', 'result', 'reason', 'hold_days']].copy()
    show_df['close_time'] = show_df['close_time'].dt.strftime('%m/%d %H:%M')
    show_df['pnl_pct']    = show_df['pnl_pct'].apply(lambda x: f"{x:+.2f}%")
    show_df['pnl_krw']    = show_df['pnl_krw'].apply(lambda x: f"{x:+,.0f}원")
    st.dataframe(show_df, use_container_width=True, hide_index=True)


# ── 메인 render() ────────────────────────────────────────────
def render():
    st.markdown("### Paper Trading — V1 / V2 / V3 스윙 전략 비교")

    # 모든 버전 데이터 로드
    all_pf  = {v: _load_pf(v)     for v in VERSIONS}
    all_pos = {v: _load_pos(v)    for v in VERSIONS}
    all_df  = {v: _load_trades(v) for v in VERSIONS}
    all_stats = {
        v: _stats(all_df[v], all_pf[v], all_pos[v])
        for v in VERSIONS
    }

    running = [v for v in VERSIONS if all_pf[v]]
    if not running:
        st.info("아직 실행된 버전이 없습니다. `run_paper_v1.bat` / `v2` / `v3` 중 하나를 실행하세요.")
        st.code("run_paper_v1.bat   # 터미널 1\n"
                "run_paper_v2.bat   # 터미널 2\n"
                "run_paper_v3.bat   # 터미널 3")
        return

    # ── 버전 비교 KPI 카드 ─────────────────────────────────────
    st.markdown("#### 버전별 성과 요약")
    cols = st.columns(len(VERSIONS))
    for col, (v, label) in zip(cols, VERSIONS.items()):
        s = all_stats[v]
        with col:
            color = VERSION_COLOR[v]
            ret_color = '#26a69a' if s['ret_pct'] >= 0 else '#ef5350'
            st.markdown(f"""
            <div style='background:#1e222d;border:1px solid {color};
                        border-radius:6px;padding:12px;'>
              <div style='font-size:11px;color:{color};font-weight:700;
                          margin-bottom:6px;'>{label}</div>
              <div style='font-size:20px;font-weight:700;color:#d1d4dc;'>
                {s['total_now']/1e4:.1f}만원
              </div>
              <div style='font-size:12px;color:{ret_color};'>
                {s['ret_pct']:+.2f}%
              </div>
              <hr style='border-color:#2a2e39;margin:8px 0;'>
              <div style='font-size:11px;color:#787b86;line-height:1.8;'>
                거래: {s['total_tr']}건 &nbsp;|&nbsp; 승률: {s['wr']:.1f}%<br>
                PF: {s['pf']:.2f} &nbsp;|&nbsp; 기대값: {s['expectancy']:+,.0f}원<br>
                오픈: {s['open_pos']}개 &nbsp;|&nbsp; 시작: {s['start'][:10]}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── 비교 차트 ──────────────────────────────────────────────
    has_trades = any(not all_df[v].empty for v in VERSIONS)
    if has_trades:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.plotly_chart(
                _cumulative_pnl_chart(all_df),
                use_container_width=True,
                config={'displayModeBar': False},
            )
        with c2:
            st.plotly_chart(
                _version_bar_chart(all_stats, 'wr', '버전별 승률', '%'),
                use_container_width=True,
                config={'displayModeBar': False},
            )
        with c3:
            st.plotly_chart(
                _version_bar_chart(all_stats, 'pf', '버전별 Profit Factor'),
                use_container_width=True,
                config={'displayModeBar': False},
            )
        st.markdown("---")

    # ── 버전별 상세 탭 ─────────────────────────────────────────
    tab_labels = [VERSIONS[v] for v in VERSIONS] + ["비교 테이블"]
    tabs = st.tabs(tab_labels)

    for i, (v, label) in enumerate(VERSIONS.items()):
        with tabs[i]:
            _render_version_detail(v)

    # 비교 테이블 탭
    with tabs[-1]:
        st.markdown("#### 버전별 상세 비교")
        rows = []
        for v, label in VERSIONS.items():
            s = all_stats[v]
            if not all_pf[v]:
                rows.append({'버전': label, '상태': '미실행'})
                continue
            rows.append({
                '버전':       label,
                '총 자산':    f"{s['total_now']/1e4:.1f}만",
                '수익률':     f"{s['ret_pct']:+.2f}%",
                '실현손익':   f"{s['realized']/1e4:+.1f}만",
                '거래수':     s['total_tr'],
                '승률':       f"{s['wr']:.1f}%",
                'PF':         s['pf'],
                '기대값':     f"{s['expectancy']:+,.0f}원",
                '평균승':     f"{s['avg_win']:+,.0f}원",
                '평균패':     f"{s['avg_loss']:+,.0f}원",
                '오픈':       s['open_pos'],
            })
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True, hide_index=True)

        # 최우수 버전 하이라이트
        ranked = [(v, all_stats[v].get('realized', 0))
                  for v in VERSIONS if all_pf[v]]
        if ranked:
            ranked.sort(key=lambda x: x[1], reverse=True)
            best_v, best_pnl = ranked[0]
            color = VERSION_COLOR[best_v]
            st.markdown(f"""
            <div style='background:rgba(38,166,154,0.1);border:1px solid {color};
                        border-radius:6px;padding:10px 14px;margin-top:12px;'>
              <span style='color:{color};font-weight:700;'>★ 현재 최우수:</span>
              <span style='color:#d1d4dc;margin-left:8px;font-weight:600;'>
                {VERSIONS[best_v]}
              </span>
              <span style='color:#787b86;margin-left:12px;'>
                실현손익 {best_pnl/1e4:+.1f}만원
              </span>
            </div>
            """, unsafe_allow_html=True)
