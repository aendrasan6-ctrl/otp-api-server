@echo off
title MY OTP API SERVER
echo.
echo ============================================================
echo   MY OTP API SERVER — Avvio
echo ============================================================
echo.
cd /d "%~dp0"
python api_server.py
pause
