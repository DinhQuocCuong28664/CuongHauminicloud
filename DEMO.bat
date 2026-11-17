@echo off
title MYMINICLOUD - LIVE DEMO CONTROLLER
color 0B
cd /d "%~dp0"
if exist "CuongHauminicloud" cd /d "%~dp0CuongHauminicloud"
python scripts\demo_menu.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Python encountered an error.
    pause
)
