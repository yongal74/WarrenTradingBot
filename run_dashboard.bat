@echo off
cd /d "%~dp0"
echo ====================================
echo  WarrenTradingActivebot Dashboard
echo  http://localhost:8501
echo ====================================
python -m streamlit run dashboard/app.py --server.port 8501 --server.headless false
pause
