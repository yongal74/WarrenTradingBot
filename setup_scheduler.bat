@echo off
chcp 65001 > nul
echo ============================================================
echo   Warren Forward Tester - 매일 자동 실행 스케줄러 등록
echo   실행 시간: 매일 오전 06:10 (미국 장 마감 후)
echo ============================================================

set SCRIPT_DIR=%~dp0
set PYTHON_CMD=python
set TASK_NAME=WarrenForwardTest

schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON_CMD% %SCRIPT_DIR%main.py" /sc daily /st 06:10 /f

echo.
echo 스케줄러 등록 완료.
echo 매일 오전 06:10에 자동 실행됩니다.
echo.
echo 확인: schtasks /query /tn WarrenForwardTest
pause
