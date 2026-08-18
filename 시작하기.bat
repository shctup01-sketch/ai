@echo off
chcp 65001 >nul
title AI Development Studio

cd /d "%~dp0"

echo AI Development Studio 실행 준비 중입니다...
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python(파이썬)이 설치되어 있지 않습니다.
    echo AI Development Studio를 실행하려면 Python이 필요합니다.
    echo.
    echo Python을 설치한 뒤 이 파일을 다시 실행해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo 처음 실행이므로 프로그램 환경을 준비합니다. 잠시만 기다려주세요...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo 프로그램 실행 중 문제가 발생했습니다.
        echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo.
    echo 프로그램 실행 중 문제가 발생했습니다.
    echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo 필요한 구성 요소를 설치하는 중입니다. 잠시만 기다려주세요...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo 프로그램 실행 중 문제가 발생했습니다.
        echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
)

echo AI Development Studio를 시작합니다...
echo.
python src\main.py
if errorlevel 1 (
    echo.
    echo 프로그램 실행 중 문제가 발생했습니다.
    echo 위 오류 내용을 확인한 뒤 다시 시도해주세요.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
