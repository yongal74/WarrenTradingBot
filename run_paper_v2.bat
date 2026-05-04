@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo [V2] FVG+DBB Clean Swing Paper Trading
python run_paper_v2.py
pause
