@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo ====================================
echo  WarrenTradingActivebot Daily Run
echo ====================================
python main.py
pause
