@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   WarrenTradingActivebot - 설치 시작
echo ============================================================
echo.

REM Python 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo   https://python.org 에서 Python 3.11 이상을 설치하세요.
    pause & exit /b 1
)
echo [OK] Python 확인 완료

REM pip 업그레이드
echo.
echo [1/4] pip 업그레이드 중...
python -m pip install --upgrade pip -q

REM 패키지 설치
echo [2/4] 패키지 설치 중... (수분 소요)
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [오류] 패키지 설치 실패. requirements.txt 확인 후 재시도.
    pause & exit /b 1
)
echo [OK] 패키지 설치 완료

REM 디렉토리 생성
echo [3/4] 폴더 구조 생성 중...
if not exist logs mkdir logs
if not exist reports mkdir reports
if not exist data\cache mkdir data\cache
if not exist backtest_results mkdir backtest_results
echo [OK] 폴더 생성 완료

REM .env 파일 생성
echo [4/4] 환경 설정 파일 확인 중...
if not exist .env (
    copy .env.example .env > nul
    echo [OK] .env 파일 생성됨 - 열어서 설정을 입력하세요
) else (
    echo [OK] .env 파일 이미 존재
)

echo.
echo ============================================================
echo   설치 완료!
echo ============================================================
echo.
echo   다음 단계:
echo   1. .env 파일을 메모장으로 열어 설정 입력
echo      - PAPER_CAPITAL: 가상 초기 자금 (기본 10,000,000원)
echo      - TELEGRAM_BOT_TOKEN: 텔레그램 알림용 (선택)
echo      - WEBHOOK_SECRET: TradingView 웹훅 보안키 (선택)
echo.
echo   실행 방법:
echo      run_dashboard.bat   - 대시보드 (http://localhost:8501)
echo      run_bot.bat         - 1회 수동 실행
echo      run_webhook.bat     - TradingView 웹훅 서버
echo.
pause
