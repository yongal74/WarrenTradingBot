@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================================
echo   5분봉 Intraday Confluence Backtest
echo   SL: 진입캔들 저점 (구조적, 최대 -0.8%%)
echo   TP: 구조적 저항까지 거리의 25%% 지점
echo   EOD: 15:30 진입차단 / 15:55 강제청산
echo   15종목 x 5합류점 = 75개 조합
echo ============================================================
python trading_backtest/backtest_intraday.py
echo.
echo 완료. backtest_results/ 폴더를 확인하세요.
pause
