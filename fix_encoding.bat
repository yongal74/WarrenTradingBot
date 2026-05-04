@echo off
chcp 65001 > nul
echo ============================================================
echo   Warren Bot - 한글 인코딩 영구 수정
echo   PYTHONUTF8=1 시스템 환경변수 등록
echo ============================================================
echo.

:: 현재 사용자 환경변수에 PYTHONUTF8=1 영구 등록
setx PYTHONUTF8 1
if %errorlevel%==0 (
    echo   [OK] PYTHONUTF8=1 등록 완료
) else (
    echo   [FAIL] 환경변수 등록 실패 - 관리자 권한으로 실행 필요
)

:: 현재 세션에도 즉시 적용
set PYTHONUTF8=1

:: Python 인코딩 확인
echo.
echo   현재 Python 인코딩 확인:
python -c "import sys; print('  stdout:', sys.stdout.encoding); print('  locale:', sys.getdefaultencoding())"

echo.
echo   *** 완전 적용을 위해 새 터미널/CMD 창을 열어주세요 ***
echo.
pause
