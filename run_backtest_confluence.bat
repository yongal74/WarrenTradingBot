@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================
echo   Confluence Backtest - 15종목 x 5전략
echo   TP: 25%% of ATR*2  /  SL: ATR*1  /  MAX_HOLD: 10일
echo ============================================================
python trading_backtest/backtest_confluence.py
echo.
echo 완료. backtest_results/ 폴더를 확인하세요.
pause
