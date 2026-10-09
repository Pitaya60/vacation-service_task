# Запуск на Windows одной командой:  .\start.ps1
# Нужны только Python 3.12 и Node.js 20. Docker и отдельный PostgreSQL не нужны.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; if (!(Test-Path .venv)) { python -m venv .venv }; .\.venv\Scripts\pip install -q -r requirements.txt; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm i; npm run dev"
Write-Host "Backend: http://localhost:8000/docs   Frontend: http://localhost:5173 (подождите 1-2 минуты при первом запуске)"
