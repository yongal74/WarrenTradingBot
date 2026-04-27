@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo   ngrok - TradingView 외부 연결 터널
echo ============================================================
echo.

where ngrok > nul 2>&1
if errorlevel 1 (
    echo [안내] ngrok이 설치되어 있지 않습니다.
    echo.
    echo   1. https://ngrok.com/download 에서 다운로드
    echo   2. ngrok.exe 를 이 폴더에 복사하거나 PATH에 추가
    echo   3. 이 파일을 다시 실행
    echo.
    pause & exit /b 1
)

echo [실행] ngrok http 8080
echo.
echo   시작 후 표시되는 "Forwarding" 주소를 복사해서
echo   TradingView Alert URL 에 붙여넣으세요.
echo.
echo   예: https://xxxx-xx-xxx.ngrok-free.app/webhook
echo.
ngrok http 8080
pause
