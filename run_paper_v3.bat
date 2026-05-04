@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo [V3] EMA Pullback New Strategy Swing Paper Trading
python run_paper_v3.py
pause
