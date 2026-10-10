@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo === vacation-tracker: starting ===

set "PYCMD="
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
  if not defined PYCMD (
    py -%%V --version >nul 2>&1 && set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  python -c "import sys;sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)" >nul 2>&1 && set "PYCMD=python"
)
if not defined PYCMD (
  echo.
  echo [ERROR] Python 3.10 or newer not found.
  echo Install Python from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
  echo and open a NEW window, then run start.bat again.
  pause
  exit /b 1
)
echo Python: %PYCMD%

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node 20 LTS from https://nodejs.org and open a NEW window.
  pause
  exit /b 1
)

start "vacation backend :8000" cmd /k "cd /d %~dp0backend && %PYCMD% -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt && .venv\Scripts\python -m uvicorn app.main:app --port 8000 || (echo. & echo [BACKEND FAILED] copy the text above & pause)"
start "vacation frontend :5173" cmd /k "cd /d %~dp0frontend && npm.cmd install && npm.cmd run dev || (echo. & echo [FRONTEND FAILED] copy the text above & pause)"

echo.
echo Two windows opened. First start takes 1-3 minutes.
echo Backend check: http://localhost:8000/api/v1/health   Frontend: http://localhost:5173
pause
