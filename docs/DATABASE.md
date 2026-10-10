# Database Design (PostgreSQL; запасной режим SQLite)

Основная СУБД — PostgreSQL (встроенный через pixeltable-pgserver, в среде Claude это 18.4, или внешний по `DATABASE_URL`). Если встроенный не стартовал, backend использует SQLite с той же схемой: миграции для SQLite автоматически подменяют `serial` и `timestamptz`; даты читаются как `date`, транзакции делает `db.connection()`. Различие: вместо `LISTEN/NOTIFY` — обратный вызов в процессе.

- `users(id, login unique, pass_hash, name, role in employee|manager|hr, hire_date, team, manager_id → users)`
- `vacations(id, user_id → users, status in pending|approved|rejected|cancelled, comment, replaces_id → vacations, created_at)`
- `vacation_parts(id, vacation_id → vacations on delete cascade, start_date, end_date, check end>=start)` — части отпуска; индекс по vacation_id.
- `notifications(id, type, vacation_id, recipient_id, text, created_at, read_at, unique(type, vacation_id, recipient_id))` — уникальный ключ = «ровно одно»; `read_at` пустой, пока пользователь не открыл уведомления (миграция 002).
- `sessions(token_hash pk, user_id → users, expires_at)` — вход пользователя; хранится SHA-256 токена, не сам токен; перезапуск backend не разлогинивает (миграция 003).
- `schema_migrations(version pk, name, applied_at)` — какие миграции уже применены.

**Целостность:** внешние ключи, check на роли и статусы, check дат, unique на логин и уведомления.
**Транзакции:** создание заявки (заявка + части), отмена и перенос выполняются в одной транзакции; согласование — одним `update ... where status='pending'`.
**Остаток** не хранится: `accrued(hire_date, date)` минус дни частей не отклонённых заявок. Отменённые после начала заявки сохраняют использованные части.
**Seed:** 4 пользователя создаются при первом старте. **Миграции:** собственный небольшой механизм вместо Alembic (SQLAlchemy в проекте нет, SQL пишется напрямую): файлы `backend/app/migrations/NNN_имя.sql` применяются при старте по порядку один раз, версии пишутся в `schema_migrations`; одни и те же файлы работают и на PostgreSQL, и на SQLite. `001_init.sql` — исходная схема, `002_notification_read.sql`, `003_sessions.sql`. Откатов (down-миграций) нет.
