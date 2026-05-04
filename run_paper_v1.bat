@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo [V1] FVG+OB Bug-Fixed Swing Paper Trading
python run_paper_v1.py
pause
