# -*- coding: utf-8 -*-
"""
Warren 학습 루프 — 필터 발굴 엔진
매일 06:05 자동 실행

핵심 목표:
  "어떤 필터 조합이 Real 진입을 만드는가"를 데이터로 증명

분석:
  1. 필터별 WIN율 (있을 때 vs 없을 때 차이)
  2. Fake 패턴 (SL 맞은 거래의 공통 조건)
  3. Real 패턴 (TP 도달한 거래의 공통 조건)
  4. 시간대 × 볼륨 × 신호타입 조합 분석
  5. 자동 파라미터 조정 제안
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np

BASE_DIR    = Path(__file__).parent
LOG_DIR     = BASE_DIR / 'logs'
TRADES_FILE = LOG_DIR / 'paper_trades.csv'
REPORT_FILE = LOG_DIR / 'learning_report.json'
PARAMS_FILE = LOG_DIR / 'strategy_params.json'

DEFAULT_PARAMS = {
    'min_quality_score':    4,
    'required_filters':     [],        # 필수 필터 (학습으로 발굴)
    'excluded_hours_kst':   [],        # 제외 시간대 (학습으로 발굴)
    'max_daily_trades':     10,
    'position_size_pct':    0.10,
    'rr_ratio':             2.0,
    'updated_at':           '',
    'version':              1,
    'discovery_log':        [],        # 발굴된 필터 이력
}

# 분석할 필터 목록
FILTER_COLS = [
    'has_vol_spike', 'has_liq_sweep', 'has_choch', 'has_body_in_zone',
    'has_pinbar', 'has_ema_align', 'has_fresh_zone',
]
FILTER_LABELS = {
    'has_vol_spike':    'Vol_Spike (볼륨 급등)',
    'has_liq_sweep':    'Liq_Sweep (유동성 스윕)',
    'has_choch':        'CHoCH (구조 전환)',
    'has_body_in_zone': 'Body_In_Zone (몸통 구간 마감)',
    'has_pinbar':       'PinBar (핀바 구조)',
    'has_ema_align':    'EMA_Align (정배열)',
    'has_fresh_zone':   'Fresh_Zone (첫 접촉)',
}


def _load_trades(days: int = 14) -> pd.DataFrame:
    if not TRADES_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(TRADES_FILE, encoding='utf-8-sig', on_bad_lines='skip')
        df['close_time'] = pd.to_datetime(df['close_time'], errors='coerce')
        df = df.dropna(subset=['close_time'])
        cutoff = datetime.now() - timedelta(days=days)
        return df[df['close_time'] >= cutoff].copy()
    except Exception:
        return pd.DataFrame()


def _load_params() -> dict:
    if PARAMS_FILE.exists():
        try:
            return json.loads(PARAMS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return dict(DEFAULT_PARAMS)


def _save_params(params: dict):
    params['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    PARAMS_FILE.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding='utf-8')


def analyze_filters(df: pd.DataFrame) -> dict:
    """필터별 WIN율 분석 — 핵심 발굴 엔진"""
    results = {}
    n_total = len(df)
    n_win   = (df['result'] == 'WIN').sum()

    for col in FILTER_COLS:
        if col not in df.columns:
            continue
        with_filter    = df[df[col] == True]
        without_filter = df[df[col] == False]

        wr_with    = (with_filter['result'] == 'WIN').mean() * 100 if len(with_filter) > 0 else 0
        wr_without = (without_filter['result'] == 'WIN').mean() * 100 if len(without_filter) > 0 else 0
        diff       = wr_with - wr_without
        n_with     = len(with_filter)

        results[col] = {
            'label':       FILTER_LABELS.get(col, col),
            'wr_with':     round(wr_with, 1),
            'wr_without':  round(wr_without, 1),
            'diff':        round(diff, 1),
            'n_with':      n_with,
            'importance':  '★★★' if diff >= 20 else ('★★' if diff >= 10 else ('★' if diff >= 5 else '')),
        }

    # 중요도 순 정렬
    return dict(sorted(results.items(), key=lambda x: x[1]['diff'], reverse=True))


def analyze_fake_patterns(df: pd.DataFrame) -> dict:
    """Fake(SL) 패턴 vs Real(TP) 패턴 분석"""
    fakes = df[df['close_reason'] == 'SL']
    reals = df[df['close_reason'] == 'TP']

    patterns = {}

    # 시간대 분석
    if 'entry_hour_kst' in df.columns:
        fake_hours = fakes['entry_hour_kst'].value_counts().head(5).to_dict() if not fakes.empty else {}
        real_hours = reals['entry_hour_kst'].value_counts().head(5).to_dict() if not reals.empty else {}
        patterns['fake_hours'] = {int(k): int(v) for k, v in fake_hours.items()}
        patterns['real_hours'] = {int(k): int(v) for k, v in real_hours.items()}

    # 신호 타입별 (FVG vs OB)
    if 'signal_type' in df.columns:
        for sig_type in ['FVG', 'OB']:
            sub = df[df['signal_type'] == sig_type]
            if len(sub) >= 3:
                wr = (sub['result'] == 'WIN').mean() * 100
                patterns[f'{sig_type}_wr'] = round(wr, 1)
                patterns[f'{sig_type}_n']  = len(sub)

    # 타임프레임별
    if 'timeframe' in df.columns:
        for tf, grp in df.groupby('timeframe'):
            if len(grp) >= 3:
                wr = (grp['result'] == 'WIN').mean() * 100
                patterns[f'tf_{tf}_wr'] = round(wr, 1)

    # 볼륨비율 분포 (WIN vs LOSS)
    if 'vol_ratio' in df.columns:
        fake_vol = fakes['vol_ratio'].mean() if not fakes.empty else 0
        real_vol = reals['vol_ratio'].mean() if not reals.empty else 0
        patterns['fake_avg_vol_ratio'] = round(fake_vol, 2)
        patterns['real_avg_vol_ratio'] = round(real_vol, 2)

    # 품질점수별
    if 'quality_score' in df.columns:
        for q, grp in df.groupby('quality_score'):
            if len(grp) >= 3:
                wr = (grp['result'] == 'WIN').mean() * 100
                patterns[f'q{int(q)}_wr'] = round(wr, 1)

    return patterns


def auto_adjust(df: pd.DataFrame, filter_analysis: dict, patterns: dict, params: dict) -> list:
    """분석 결과 기반 자동 파라미터 조정"""
    adjustments = []
    n = len(df)
    if n < 5:
        return ['데이터 부족 (최소 5건 필요) — 계속 수집 중']

    overall_wr = (df['result'] == 'WIN').mean() * 100

    # 1. 핵심 필터 발굴 — WIN율 차이 20%p 이상이면 필수 필터로 등록
    for col, data in filter_analysis.items():
        if data['diff'] >= 20 and data['n_with'] >= 3:
            filter_name = col.replace('has_', '')
            if filter_name not in params.get('required_filters', []):
                params.setdefault('required_filters', []).append(filter_name)
                adjustments.append(
                    f"[필수 필터 발굴] {data['label']}: "
                    f"있을때 WR {data['wr_with']}% vs 없을때 {data['wr_without']}% "
                    f"(+{data['diff']}%p) → 진입 필수 조건 추가"
                )

    # 2. Fake 시간대 발굴 — 특정 시간 LOSS 집중이면 제외
    fake_hours = patterns.get('fake_hours', {})
    real_hours = patterns.get('real_hours', {})
    for hour, count in fake_hours.items():
        real_count = real_hours.get(hour, 0)
        if count >= 3 and count > real_count * 2:
            if hour not in params.get('excluded_hours_kst', []):
                params.setdefault('excluded_hours_kst', []).append(hour)
                adjustments.append(f"[시간대 제외] KST {hour}시: Fake {count}건 vs Real {real_count}건 → 제외")

    # 3. 전체 승률 기반 품질 기준 조정
    if overall_wr < 50 and n >= 10:
        new_q = min(params['min_quality_score'] + 1, 7)
        if new_q != params['min_quality_score']:
            params['min_quality_score'] = new_q
            adjustments.append(f"[품질 상향] 승률 {overall_wr:.1f}% < 50% → 최소 {new_q}점으로 상향")
    elif overall_wr >= 70 and n >= 10 and params['min_quality_score'] > 3:
        new_q = params['min_quality_score'] - 1
        params['min_quality_score'] = new_q
        adjustments.append(f"[품질 하향] 승률 {overall_wr:.1f}% >= 70% → 최소 {new_q}점으로 하향 (기회 확대)")

    # 4. FVG vs OB 성과 비교
    fvg_wr = patterns.get('FVG_wr', 0)
    ob_wr  = patterns.get('OB_wr', 0)
    fvg_n  = patterns.get('FVG_n', 0)
    ob_n   = patterns.get('OB_n', 0)
    if fvg_n >= 3 and ob_n >= 3:
        if fvg_wr > ob_wr + 15:
            adjustments.append(f"[신호 선호] FVG WR {fvg_wr}% >> OB {ob_wr}% → FVG 신호 우선 진입 권장")
        elif ob_wr > fvg_wr + 15:
            adjustments.append(f"[신호 선호] OB WR {ob_wr}% >> FVG {fvg_wr}% → OB 신호 우선 진입 권장")

    return adjustments if adjustments else ['이상 없음 — 현재 전략 유지']


def print_report(df: pd.DataFrame, filter_analysis: dict, patterns: dict,
                 adjustments: list, params: dict):
    n  = len(df)
    wr = (df['result'] == 'WIN').mean() * 100 if n > 0 else 0
    total_pnl = df['pnl_krw'].sum() if n > 0 else 0

    print(f"\n{'='*65}")
    print(f"  Warren 필터 발굴 리포트 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    print(f"  최근 14일 | {n}건 | 승률 {wr:.1f}% | 손익 {total_pnl/1e4:+.1f}만원")
    print(f"{'='*65}")

    print(f"\n  [필터별 WIN율 분석 — Real vs Fake 판별력]")
    print(f"  {'필터':<28} {'있을때':>7} {'없을때':>7} {'차이':>7} {'중요도'}")
    print(f"  {'-'*60}")
    for col, d in filter_analysis.items():
        if d['n_with'] == 0:
            continue
        print(f"  {d['label']:<28} {d['wr_with']:>6.1f}%  {d['wr_without']:>6.1f}%  "
              f"{d['diff']:>+6.1f}%p  {d['importance']}")

    print(f"\n  [Fake vs Real 패턴]")
    if patterns.get('fake_hours'):
        print(f"  Fake 집중 시간대 (KST): {dict(list(patterns['fake_hours'].items())[:3])}")
    if patterns.get('real_hours'):
        print(f"  Real 집중 시간대 (KST): {dict(list(patterns['real_hours'].items())[:3])}")
    if patterns.get('fake_avg_vol_ratio'):
        print(f"  볼륨비율 — Fake평균: {patterns['fake_avg_vol_ratio']:.2f}x  "
              f"Real평균: {patterns.get('real_avg_vol_ratio', 0):.2f}x")

    fvg_wr = patterns.get('FVG_wr')
    ob_wr  = patterns.get('OB_wr')
    if fvg_wr and ob_wr:
        print(f"  FVG WR: {fvg_wr}% ({patterns.get('FVG_n',0)}건)  |  "
              f"OB WR: {ob_wr}% ({patterns.get('OB_n',0)}건)")

    print(f"\n  [타임프레임별]")
    for key in ['tf_4h_wr', 'tf_15m_wr', 'tf_5m_wr']:
        val = patterns.get(key)
        if val:
            print(f"  {key.replace('tf_','').replace('_wr',''):<6} WR: {val}%")

    print(f"\n  [자동 조정 & 발굴 결과]")
    for adj in adjustments:
        prefix = '  *** ' if '발굴' in adj or '필수' in adj else '  * '
        print(f"{prefix}{adj}")

    if params.get('required_filters'):
        print(f"\n  [현재 필수 필터 목록] (발굴된 Real 진입 조건)")
        for f in params['required_filters']:
            print(f"  → {f}")

    if params.get('excluded_hours_kst'):
        print(f"\n  [제외 시간대] KST {params['excluded_hours_kst']}시")

    print(f"\n  [파라미터 v{params.get('version',1)}]")
    print(f"  품질 최소: {params['min_quality_score']}점  |  "
          f"일 최대: {params['max_daily_trades']}건  |  "
          f"포지션: {params['position_size_pct']*100:.0f}%")
    print(f"{'='*65}\n")


def run():
    print(f"\n  학습 루프 실행 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

    params = _load_params()
    df     = _load_trades(days=14)

    if df.empty or len(df) < 3:
        print(f"  데이터 부족 ({len(df)}건) — 페이퍼 트레이딩 계속 진행 중")
        print(f"  최소 5건 이상 완료 후 분석 시작")
        return

    print(f"  {len(df)}건 분석 중...")

    filter_analysis = analyze_filters(df)
    patterns        = analyze_fake_patterns(df)
    adjustments     = auto_adjust(df, filter_analysis, patterns, params)

    print_report(df, filter_analysis, patterns, adjustments, params)

    # 리포트 저장
    report = {
        'date':            datetime.now().strftime('%Y-%m-%d'),
        'total_trades':    len(df),
        'win_rate':        round((df['result'] == 'WIN').mean() * 100, 1) if len(df) > 0 else 0,
        'total_pnl_krw':   round(df['pnl_krw'].sum()) if len(df) > 0 else 0,
        'filter_analysis': filter_analysis,
        'patterns':        patterns,
        'adjustments':     adjustments,
        'params_version':  params.get('version', 1),
    }

    history = []
    if REPORT_FILE.exists():
        try:
            history = json.loads(REPORT_FILE.read_text(encoding='utf-8'))
        except Exception:
            history = []
    history.append(report)
    REPORT_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')

    if any('이상 없음' not in a for a in adjustments):
        params['version'] = params.get('version', 1) + 1
        disc = params.setdefault('discovery_log', [])
        disc.append({'date': datetime.now().strftime('%Y-%m-%d'), 'changes': adjustments})
        _save_params(params)
        print(f"  파라미터 v{params['version']} 저장 완료")
    else:
        print(f"  조정 없음 — 현재 전략 유지")


if __name__ == '__main__':
    run()
