@echo off
cd /d "%~dp0"
title TransDubaiTestBot Launcher
powershell -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
pause
