@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

echo ============================================
echo       Lou - Instalador Automatico
echo ============================================
echo.

:: ---- Verifica Python ----
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.11+ em https://www.python.org/downloads/
    echo Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

:: ---- Mostra versao do Python ----
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] %PYVER% encontrado.
echo.

:: ---- Cria venv se nao existir ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Criando ambiente virtual .venv ...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao criar venv. Verifique sua instalacao do Python.
        pause
        exit /b 1
    )
    echo       Venv criada com sucesso.
) else (
    echo [1/4] Venv .venv ja existe. Pulando criacao.
)
echo.

:: ---- Ativa venv ----
echo [2/4] Ativando venv ...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao ativar a venv.
    pause
    exit /b 1
)
echo       Venv ativada.
echo.

:: ---- Atualiza pip ----
echo [3/4] Atualizando pip ...
python -m pip install --upgrade pip --quiet
echo       pip atualizado.
echo.

:: ---- Instala llama-cpp-python (CUDA 12.4) ----
echo [4/4] Instalando llama-cpp-python v0.3.4 com suporte CUDA 12.4 ...
echo       (Isso pode levar alguns minutos na primeira vez)
echo.

pip install llama-cpp-python==0.3.4 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 --quiet
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AVISO] Falha ao instalar com CUDA 12.4.
    echo         Tentando instalar versao CPU como fallback ...
    pip install llama-cpp-python==0.3.4 --quiet
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao instalar llama-cpp-python.
        echo        Verifique sua conexao com a internet e tente novamente.
        pause
        exit /b 1
    )
    echo       llama-cpp-python instalado (modo CPU).
) else (
    echo       llama-cpp-python instalado com CUDA 12.4.
)
echo.

:: ---- Cria pasta models se nao existir ----
if not exist "models" (
    mkdir models
    echo [INFO] Pasta "models" criada. Coloque seus arquivos .gguf nela.
) else (
    echo [INFO] Pasta "models" ja existe.
)
echo.

:: ---- Resumo ----
echo ============================================
echo       Instalacao concluida!
echo ============================================
echo.
echo Para iniciar o Lou:
echo   1. Coloque um modelo .gguf na pasta "models\"
echo   2. Configure o caminho em neve-frontend\backend\settings.py
echo   3. Execute: .venv\Scripts\python.exe run_neve_frontend.py
echo.
echo Ou simplesmente execute: start.bat (se disponivel)
echo ============================================
pause
