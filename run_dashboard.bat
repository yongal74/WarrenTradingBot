@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo ====================================
echo  WarrenTradingActivebot Dashboard
echo  http://localhost:8501
echo ====================================
python -m streamlit run dashboard/app.py --server.port 8501 --server.headless false
pause
