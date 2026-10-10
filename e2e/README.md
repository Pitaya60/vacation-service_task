# Сквозные тесты интерфейса

Проверяют настоящий интерфейс в Chromium: ошибка правил в форме, заявка → руководитель без перезагрузки (SSE), отказ с причиной, правка даты выхода у HR, счётчик непрочитанных уведомлений, мобильная ширина.

```
pip install playwright pytest
playwright install chromium

# 1) backend (любой БД; для чистого запуска SQLite):
cd backend && set VAC_DB=sqlite && python -m uvicorn app.main:app --port 8000
# 2) frontend:
cd frontend && npm run build && npx vite preview --port 4173
# 3) тесты (из корня репозитория):
python -m pytest e2e -q
```

Скриншоты в папку: переменная `E2E_SHOTS=docs/screenshots`. Адрес frontend: `E2E_URL` (по умолчанию http://localhost:4173).
