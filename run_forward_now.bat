@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================
echo   Forward Testing - 지금 즉시 1회 실행 (미국장)
echo   합류점 로직 + TP 25%% + 손절 1xATR
echo ============================================================
python main.py once
echo.
pause
