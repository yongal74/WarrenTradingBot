@echo off
chcp 65001 > nul
title Warren Trading Bot — Launcher
cd /d "%~dp0"

echo.
echo ============================================================
echo   Warren FVG+OB Trading Bot v2.0
echo   KR + US + CRYPTO Auto Trader
echo ============================================================
echo.

:: logs 폴더
if not exist logs mkdir logs
if not exist backtest_results mkdir backtest_results
if not exist data\cache mkdir data\cache

echo [1/5] 매크로 국면 체크 (Pillar 1)...
python -c "from core.macro_regime import get_regime; r,d=get_regime(); print(f'  Regime: [{r}]  VIX={d[\"vix\"]:.1f}  US10Y={d[\"t10y\"]:.2f}%%  KRW={d[\"krw\"]:.0f}')" 2>nul
echo.

echo [2/5] FVG+OB 스캔 (KR5+US5+CRYPTO4)...
start /min cmd /c "python run_forward_daily.py > logs\scanner.log 2>&1"
timeout /t 3 /nobreak > nul
echo       logs\scanner.log 참조

echo [3/5] 대시보드 시작...
start /min cmd /c "python -m streamlit run dashboard/app.py --server.port 8501 > logs\dashboard.log 2>&1"
timeout /t 4 /nobreak > nul
echo       http://localhost:8501

echo [4/5] 웹훅 서버 시작...
start /min cmd /c "python webhook_server.py > logs\webhook.log 2>&1"
timeout /t 2 /nobreak > nul
echo       http://localhost:8080/webhook

echo [5/5] 브라우저 열기...
timeout /t 2 /nobreak > nul
start http://localhost:8501

echo.
echo ============================================================
echo   Warren Bot v3.0 — 실행 완료
echo.
echo   대시보드:    http://localhost:8501
echo   스캔로그:    logs\scanner.log
echo   신호기록:    logs\forward_signals.csv
echo   학습기록:    logs\learning_log.csv
echo.
echo   자동스케줄:  setup_scheduler.bat (관리자권한)
echo     09:05 한국장 스캔  15:35 복기학습  22:35 미국장 스캔
echo ============================================================
echo.
pause
