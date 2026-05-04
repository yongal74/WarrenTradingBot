@echo off
chcp 65001 > nul
echo ============================================================
echo   Warren Bot - 자동 실행 스케줄러 등록 (관리자 권한 필요)
echo ============================================================
echo.

set DIR=C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0

REM 아침 투자일지 브리핑 07:00 (변경: 09:00 -> 07:00)
schtasks /create /tn "Warren_Journal_Morning" /tr "python \"%DIR%\run_journal.py\" --session morning" /sc DAILY /st 07:00 /rl HIGHEST /f
echo [OK] 아침 투자일지 브리핑 07:00 등록

REM KR 마감 복기 17:00
schtasks /create /tn "Warren_Journal_Afternoon" /tr "python \"%DIR%\run_journal.py\" --session afternoon" /sc DAILY /st 17:00 /rl HIGHEST /f
echo [OK] KR 마감 복기 17:00 등록

REM 전체 복기 + Lessons Learned 21:00
schtasks /create /tn "Warren_Journal_Evening" /tr "python \"%DIR%\run_journal.py\" --session evening" /sc DAILY /st 21:00 /rl HIGHEST /f
echo [OK] 전체 복기 + Lessons Learned 21:00 등록

REM 한국장 스캔 09:05
schtasks /create /tn "Warren_Scanner_KR" /tr "\"%DIR%\run_scanner.bat\"" /sc DAILY /st 09:05 /rl HIGHEST /f
echo [OK] 한국장 스캐너 09:05 등록

REM 복기/학습 에이전트 15:35
schtasks /create /tn "Warren_Learning" /tr "\"%DIR%\run_learning.bat\"" /sc DAILY /st 15:35 /rl HIGHEST /f
echo [OK] 복기 학습 에이전트 15:35 등록

REM 미국장 스캔 22:35
schtasks /create /tn "Warren_Scanner_US" /tr "\"%DIR%\run_scanner.bat\"" /sc DAILY /st 22:35 /rl HIGHEST /f
echo [OK] 미국장 스캐너 22:35 등록

echo.
echo 등록된 Warren 작업:
schtasks /query /fo LIST /tn "Warren_Journal_Morning" 2>nul
schtasks /query /fo LIST /tn "Warren_Scanner_KR" 2>nul
schtasks /query /fo LIST /tn "Warren_Learning"   2>nul
schtasks /query /fo LIST /tn "Warren_Scanner_US" 2>nul
echo.
pause
