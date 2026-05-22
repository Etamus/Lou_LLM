@echo off
chcp 65001 >nul 2>&1
setlocal

cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PowerShell nao encontrado.
    pause
    exit /b 1
)

powershell -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERRO] O instalador terminou com codigo %EXITCODE%.
    pause
)

exit /b %EXITCODE%
