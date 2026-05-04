@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo [Warren] FVG+OB 스캔 시작 %date% %time%
python run_forward_daily.py
echo [Warren] 스캔 완료 %time%
