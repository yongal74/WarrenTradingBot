@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0"
python -X utf8 run_master_loop.py >> logs\master_loop.log 2>&1
