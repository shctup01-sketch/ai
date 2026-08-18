@echo off
chcp 65001 >nul
title AI Development Studio

echo AI Development Studio 시작 중...
echo.

cd /d "%~dp0"
if errorlevel 1 (
    echo 프로젝트 폴더로 이동하지 못했습니다.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

echo 현재 폴더:
echo %CD%
echo.

echo [1/5] Python 확인 중...
set "PYTHON_CMD="
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        set "PYTHON_CMD="
    ) else (
        set "PYTHON_CMD=py"
    )
) else (
    set "PYTHON_CMD=python"
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo Python^(파이썬^)을 찾을 수 없습니다.
    echo python 또는 py 명령을 확인했습니다.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo     -^> Python 확인 완료 ^( %PYTHON_CMD% 명령 사용 ^)
echo.

echo [2/5] 가상환경 확인 중...
if not exist "venv\Scripts\python.exe" (
    echo     -^> 가상환경이 없어 새로 만듭니다. 잠시만 기다려주세요...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo.
        echo 프로그램 실행 중 문제가 발생했습니다. ^( 가상환경 생성 실패 ^)
        echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
) else (
    echo     -^> 기존 가상환경을 사용합니다.
)
echo.

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo.
    echo 프로그램 실행 중 문제가 발생했습니다. ^( 가상환경 활성화 실패 ^)
    echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

echo [3/5] 필요한 패키지 확인 중...
echo     -^> requirements.txt 기준으로 확인합니다. 잠시만 기다려주세요...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 프로그램 실행 중 문제가 발생했습니다. ^( 패키지 설치 실패 ^)
    echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo     -^> 필요한 패키지가 모두 준비되었습니다.
echo.

echo [4/5] 프로그램 실행 준비 중...
if not exist "src\main.py" (
    echo.
    echo 프로그램 파일 src\main.py 을 찾을 수 없습니다.
    echo 프로젝트 폴더가 올바른지 확인해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo     -^> 실행 파일 확인 완료.
echo.

echo [5/5] AI Development Studio 실행 중...
echo.
python src\main.py
set "APP_EXIT_CODE=%errorlevel%"

echo.
if not "%APP_EXIT_CODE%"=="0" (
    echo 프로그램 실행 중 문제가 발생했습니다. ^( 종료 코드: %APP_EXIT_CODE% ^)
    echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

echo 프로그램이 종료되었습니다.
echo 창을 닫으려면 아무 키나 누르세요.
pause >nul
