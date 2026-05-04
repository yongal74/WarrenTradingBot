@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0"
python -X utf8 run_learning_loop.py >> logs\learning_loop.log 2>&1
