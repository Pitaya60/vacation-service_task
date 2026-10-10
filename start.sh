#!/usr/bin/env bash
# Запуск на macOS/Linux: backend (:8000) и frontend (:5173) в одном окне терминала. Остановка: Ctrl+C.
# Аналог start.bat для Windows. Нужны Python 3.10+ и Node.js 20+; Docker и отдельный PostgreSQL не нужны.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then echo "[ERROR] Не найден Python 3.10 или новее (https://www.python.org/downloads/). Свой интерпретатор: PYTHON=/путь/к/python ./start.sh"; exit 1; fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then echo "[ERROR] Не найден Node.js/npm. Установите Node.js 20 LTS: https://nodejs.org"; exit 1; fi
echo "=== vacation-tracker: Python $("$PY" -c 'import platform; print(platform.python_version())'), Node $(node --version) ==="

echo "--- backend: зависимости"
[ -d backend/.venv ] || "$PY" -m venv backend/.venv
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

echo "--- frontend: зависимости"
(cd frontend && npm install --no-audit --no-fund --loglevel=error)

BACKEND_PID=""
cleanup() { [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "--- backend: запуск на :8000 (первый старт поднимает встроенный PostgreSQL, до минуты)"
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --port 8000) &
BACKEND_PID=$!

for _ in $(seq 1 90); do
  if backend/.venv/bin/python -c 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=2).status == 200 else 1)' 2>/dev/null; then READY=1; break; fi
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "[ERROR] backend завершился, смотрите сообщение выше"; exit 1; }
  sleep 1
done
if [ -z "${READY:-}" ]; then echo "[ERROR] backend не ответил за 90 секунд"; exit 1; fi
echo "backend готов: http://localhost:8000/api/v1/health"

echo "--- frontend: http://localhost:5173  (вход: ivan, olga, boss, hr; пароль demo)"
cd frontend && npm run dev
