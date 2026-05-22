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

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1" %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERRO] Nao foi possivel iniciar a Lou. Codigo %EXITCODE%.
    pause
)

exit /b %EXITCODE%
