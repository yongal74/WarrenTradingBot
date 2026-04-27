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

echo [1/4] 대시보드 시작 중...
start /min cmd /c "python -m streamlit run dashboard/app.py --server.port 8501 > logs\dashboard.log 2>&1"
timeout /t 3 /nobreak > nul
echo       http://localhost:8501

echo [2/4] TradingView 웹훅 서버 시작 중...
start /min cmd /c "python webhook_server.py > logs\webhook.log 2>&1"
timeout /t 2 /nobreak > nul
echo       http://localhost:8080/webhook

echo [3/4] FVG+OB 포워드 스캐너 시작 중...
start /min cmd /c "python run_forward_daily.py > logs\scanner.log 2>&1"
timeout /t 2 /nobreak > nul
echo       KR5 + US5 신호 스캔 완료

echo [4/4] 브라우저 열기...
timeout /t 3 /nobreak > nul
start http://localhost:8501

echo.
echo ============================================================
echo   모든 서비스 실행 완료!
echo.
echo   대시보드:    http://localhost:8501
echo   웹훅서버:    http://localhost:8080
echo   외부접속:    run_ngrok.bat 실행 후 URL 확인
echo ============================================================
echo.
echo   종료하려면 이 창을 닫으세요.
pause
