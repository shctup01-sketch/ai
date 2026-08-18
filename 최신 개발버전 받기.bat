@echo off
chcp 65001 >nul
title 최신 개발버전 받기

cd /d "%~dp0"

echo 최신 개발버전 받기
echo.
echo AI Development Studio를 종료한 상태에서 업데이트해야 합니다.
echo 계속하시겠습니까?
echo.
choice /C YN /N /M "Y = 계속, N = 취소 : "
if errorlevel 2 (
    echo.
    echo 업데이트를 취소했습니다.
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 0
)

set "REPO_OWNER=shctup01-sketch"
set "REPO_NAME=ai"
set "BRANCH_NAME=claude/ai-collab-dev-setup-check-6efyve"
set "ZIP_URL=https://github.com/%REPO_OWNER%/%REPO_NAME%/archive/refs/heads/%BRANCH_NAME%.zip"

set "WORK_DIR=%TEMP%\ai_dev_update_%RANDOM%"
set "ZIP_PATH=%WORK_DIR%\update.zip"
set "EXTRACT_DIR=%WORK_DIR%\extracted"
set "BACKUP_DIR=%WORK_DIR%\backup"
set "SOURCE_ROOT=%EXTRACT_DIR%\source_root"

echo.
echo [1/5] 업데이트 준비 중...
mkdir "%WORK_DIR%" >nul 2>nul
mkdir "%EXTRACT_DIR%" >nul 2>nul
mkdir "%BACKUP_DIR%" >nul 2>nul
if not exist "%EXTRACT_DIR%" (
    echo.
    echo 업데이트 준비 중 문제가 발생했습니다. ^( 임시 폴더 생성 실패 ^)
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo     -^> 준비 완료. ^( 임시 위치: %WORK_DIR% ^)
echo.

echo [2/5] 최신 버전 다운로드 중...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_PATH%' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo 최신 버전 다운로드에 실패했습니다. ^( 인터넷 연결을 확인해주세요 ^)
    call :cleanup_temp
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
if not exist "%ZIP_PATH%" (
    echo.
    echo 최신 버전 다운로드에 실패했습니다. ^( 파일이 생성되지 않음 ^)
    call :cleanup_temp
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo.

echo [3/5] 압축 해제 중...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%EXTRACT_DIR%' -Force; $d = Get-ChildItem -Path '%EXTRACT_DIR%' -Directory | Select-Object -First 1; if (-not $d) { exit 1 }; Rename-Item -Path $d.FullName -NewName 'source_root' -ErrorAction Stop } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo 압축 해제에 실패했습니다.
    call :cleanup_temp
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
if not exist "%SOURCE_ROOT%\src" (
    echo.
    echo 다운로드한 내용에서 프로그램 파일^(src 폴더^)을 찾을 수 없습니다.
    call :cleanup_temp
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)
echo.

echo [4/5] 기존 버전 백업 중...
if exist "src" (
    robocopy "src" "%BACKUP_DIR%\src" /E /NFL /NDL /NJH /NJS >nul
    if errorlevel 8 (
        echo.
        echo 기존 버전 백업에 실패했습니다. 업데이트를 중단합니다.
        call :cleanup_temp
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
)
if exist "requirements.txt" (
    copy /y "requirements.txt" "%BACKUP_DIR%\requirements.txt" >nul
    if errorlevel 1 (
        echo.
        echo 기존 버전 백업에 실패했습니다. 업데이트를 중단합니다.
        call :cleanup_temp
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
)
echo     -^> 백업 완료.
echo.

echo [5/5] 최신 버전 적용 중...
robocopy "%SOURCE_ROOT%\src" "src" /MIR /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo.
    echo 프로그램 파일 적용에 실패했습니다. 기존 버전으로 복구합니다...
    call :restore_backup
    call :cleanup_temp
    echo.
    echo 창을 닫으려면 아무 키나 누르세요.
    pause >nul
    exit /b 1
)

if exist "%SOURCE_ROOT%\requirements.txt" (
    copy /y "%SOURCE_ROOT%\requirements.txt" "requirements.txt" >nul
    if errorlevel 1 (
        echo.
        echo 프로그램 파일 적용에 실패했습니다. 기존 버전으로 복구합니다...
        call :restore_backup
        call :cleanup_temp
        echo.
        echo 창을 닫으려면 아무 키나 누르세요.
        pause >nul
        exit /b 1
    )
)

call :cleanup_temp

echo.
echo 최신 개발버전으로 업데이트되었습니다.
echo 이제 시작하기.bat를 실행해주세요.
echo.
echo 창을 닫으려면 아무 키나 누르세요.
pause >nul
exit /b 0

:restore_backup
if exist "%BACKUP_DIR%\src" (
    robocopy "%BACKUP_DIR%\src" "src" /MIR /NFL /NDL /NJH /NJS >nul
)
if exist "%BACKUP_DIR%\requirements.txt" (
    copy /y "%BACKUP_DIR%\requirements.txt" "requirements.txt" >nul
)
exit /b 0

:cleanup_temp
if exist "%WORK_DIR%" (
    rmdir /s /q "%WORK_DIR%" >nul 2>nul
)
exit /b 0
