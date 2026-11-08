@echo off
chcp 65001 >nul
title HMZ Video Studio Pro - Developer License Tool
cd /d "%~dp0.."
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)
python tools\license_menu.py
set RC=%ERRORLEVEL%
pause
exit /b %RC%
