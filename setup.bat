@echo off
title Steel Plant HR - Setup
cd /d "%~dp0"
echo ===== Steel Plant HR : one-time setup =====
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (where python >nul 2>nul && set PY=python)
if "%PY%"=="" (
  echo Python was not found. Install Python 3.8.10 ^(last version for Windows 7^) from python.org,
  echo tick "Add Python to PATH", then run setup.bat again.
  pause & exit /b 1
)
%PY% -m venv venv
if errorlevel 1 (echo Could not create virtual environment. & pause & exit /b 1)
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Package install failed - check the internet connection. & pause & exit /b 1)
venv\Scripts\python.exe manage.py init
echo.
echo Setup finished. Start the system with run.bat
pause
