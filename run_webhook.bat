@echo off
cd /d "%~dp0"
echo ====================================
echo  WarrenBot TradingView Webhook
echo  http://localhost:8080/webhook
echo ====================================
python webhook_server.py
pause
