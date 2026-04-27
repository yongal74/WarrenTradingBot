@echo off
chcp 65001 > nul
echo ============================================================
echo   Warren FVG+OB 일일 포워드 테스터 - 자동 스케줄러 등록
echo ============================================================
echo.
echo   [스케줄]
echo   09:00  한국장 시작 신호 스캔
echo   22:30  미국장 시작 신호 스캔
echo   06:10  아침 리포트 (전일 결과 요약)
echo.

set SCRIPT_DIR=%~dp0
set PYTHON_CMD=python
set LOG_DIR=%SCRIPT_DIR%logs

:: logs 폴더 생성
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: ── 기존 태스크 삭제 (재등록을 위해) ──────────────────────────
schtasks /delete /tn "WarrenScan_KR"    /f 2>nul
schtasks /delete /tn "WarrenScan_US"    /f 2>nul
schtasks /delete /tn "WarrenReport"     /f 2>nul

:: ── 한국장 스캔: 매일 09:00 ──────────────────────────────────
schtasks /create /tn "WarrenScan_KR" ^
  /tr "\"%PYTHON_CMD%\" \"%SCRIPT_DIR%run_forward_daily.py\" >> \"%LOG_DIR%\scan_kr.log\" 2>&1" ^
  /sc daily /st 09:00 /f
if %errorlevel%==0 (
    echo   [OK] WarrenScan_KR  등록: 매일 09:00
) else (
    echo   [FAIL] WarrenScan_KR 등록 실패
)

:: ── 미국장 스캔: 매일 22:30 ──────────────────────────────────
schtasks /create /tn "WarrenScan_US" ^
  /tr "\"%PYTHON_CMD%\" \"%SCRIPT_DIR%run_forward_daily.py\" >> \"%LOG_DIR%\scan_us.log\" 2>&1" ^
  /sc daily /st 22:30 /f
if %errorlevel%==0 (
    echo   [OK] WarrenScan_US  등록: 매일 22:30
) else (
    echo   [FAIL] WarrenScan_US 등록 실패
)

:: ── 아침 리포트: 매일 06:10 ──────────────────────────────────
schtasks /create /tn "WarrenReport" ^
  /tr "\"%PYTHON_CMD%\" \"%SCRIPT_DIR%run_forward_daily.py\" --report >> \"%LOG_DIR%\report.log\" 2>&1" ^
  /sc daily /st 06:10 /f
if %errorlevel%==0 (
    echo   [OK] WarrenReport   등록: 매일 06:10
) else (
    echo   [FAIL] WarrenReport 등록 실패
)

echo.
echo ============================================================
echo   등록 완료! 확인 명령:
echo   schtasks /query /tn "WarrenScan_KR"
echo   schtasks /query /tn "WarrenScan_US"
echo   schtasks /query /tn "WarrenReport"
echo.
echo   수동 즉시 실행 테스트:
echo   python "%SCRIPT_DIR%run_forward_daily.py"
echo ============================================================
echo.
pause
