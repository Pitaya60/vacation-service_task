# Development Decision Log

- **Project:** vacation-tracker — сервис учёта отпусков (задание 13)
- **Developer:** Camilla Abdulla
- **AI assistant:** Claude Sonnet 5.5 (claude.ai, чат)
- **Backend:** Python 3.12, FastAPI, psycopg 3 · **Frontend:** React + Vite · **Database:** PostgreSQL 16
- **Repository:** (добавить URL GitHub)

Метки времени ниже — только реальные. Строки добавляются командой `python scripts/log.py "..."`. Решения 1–6 принимались в сессии 2026-10-10; точное время тогда не фиксировалось, поэтому оно не указано, чтобы не выдавать его за записанное вживую.

## Решения

### D1 — Запуск без Docker (дата сессии: 2026-10-10)
- **Проблема:** Docker Desktop на машине не запустился; первый план (Node + Docker) делал запуск зависимым от него.
- **Альтернативы:** починить Docker; ставить PostgreSQL вручную; встроенный PostgreSQL через pip.
- **Решение:** `pgserver` (pip-пакет с настоящим PostgreSQL 16) поднимается сам при старте backend; для внешней БД — `DATABASE_URL`.
- **Компромисс:** данные в `.pgdata/`, нельзя запускать от администратора Windows; для production — обычный Postgres.
- **Проверка:** запуск и 27 тестов на этом Postgres прошли в сессии Claude (Linux). На Windows пользователя — не проверено.

### D2 — Python/FastAPI вместо Node
- Требование пользователя. FastAPI даёт валидацию запросов и `/docs`; SQL пишется напрямую, без ORM: нужны `on conflict do nothing`, пересечение интервалов, `pg_notify`.

### D3 — Остаток не хранится, а считается функцией `accrued()`
- Смена даты выхода пересчитывает всё без миграций данных. Проверено тестом `test_hire_date_change_recalculates`.

### D4 — «Ровно одно» уведомление держит БД
- `unique(type, vacation_id, recipient_id)` + `on conflict do nothing`. Проверено: гонка двух согласований и двойной вызов `remind()` дают по одному уведомлению.

### D5 — SSE поверх Postgres LISTEN/NOTIFY
- Нужен только поток сервер→клиент; NOTIFY работает и при нескольких процессах. Проверено e2e-тестом на две сессии.

### D6 — Согласование атомарно
- `update ... where status='pending' returning` — второй одновременный запрос получает 409.

## Хронология (реальные метки)
