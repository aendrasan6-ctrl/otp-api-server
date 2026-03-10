@echo off
title MY OTP API SERVER — Setup
echo.
echo ============================================================
echo   MY OTP API SERVER — Installazione dipendenze
echo ============================================================
echo.

REM Controlla Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRORE] Python non trovato!
    echo Scarica Python da https://python.org e riprova.
    pause
    exit /b 1
)

echo [OK] Python trovato.
echo.
echo Installazione librerie...
pip install flask requests
echo.
echo ============================================================
echo   Installazione completata!
echo   Ora modifica api_server.py e imposta SPIDER_API_KEY
echo   poi lancia: start_server.bat
echo ============================================================
pause
