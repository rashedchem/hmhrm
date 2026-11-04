@echo off
title Steel Plant HR - Server
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (echo Please run setup.bat first. & pause & exit /b 1)
rem Use 0.0.0.0 so other PCs on the office network can connect, or 127.0.0.1 for this PC only.
set HR_HOST=0.0.0.0
set HR_PORT=8000
rem Set to 1 only when the site is served over HTTPS:
set HR_HTTPS=0
venv\Scripts\python.exe app.py
pause
