# Database Design (PostgreSQL; запасной режим SQLite)

Основная СУБД — PostgreSQL (встроенный через pixeltable-pgserver, в среде Claude это 18.x, или внешний по `DATABASE_URL`). Если встроенный не стартовал, backend использует SQLite с той же схемой: миграции для SQLite автоматически подменяют `serial` и `timestamptz`; даты читаются как `date`, транзакции делает `db.connection()`. Различие: вместо `LISTEN/NOTIFY` — обратный вызов в процессе.

- `users(id, login unique, pass_hash, name, role in employee|manager|hr, hire_date, team, manager_id → users)`
- `vacations(id, user_id → users, status in pending|approved|rejected|cancelled, comment, replaces_id → vacations, created_at, cancelled_on, cancelled_from, decided_at, decided_by → users)` — последние четыре поля добавлены миграцией 004: когда и из какого статуса отменили, кто и когда решил.
- `vacation_parts(id, vacation_id → vacations on delete cascade, start_date, end_date, check end>=start)` — части отпуска; индекс по vacation_id.
- `notifications(id, type, vacation_id, recipient_id, text, created_at, read_at, unique(type, vacation_id, recipient_id))` — уникальный ключ = «ровно одно»; `read_at` пустой, пока пользователь не открыл уведомления (миграция 002).
- `sessions(token_hash pk, user_id → users, expires_at)` — вход пользователя; хранится SHA-256 токена, не сам токен; перезапуск backend не разлогинивает (миграция 003); просроченные удаляются при входе.
- `schema_migrations(version pk, name, applied_at)` — какие миграции уже применены.
- Индексы (миграция 004): `vacations(user_id)`, `notifications(recipient_id)`, `sessions(expires_at)`.

**Целостность:** внешние ключи, check на роли и статусы, check дат, unique на логин и уведомления.
**Транзакции и гонки:** создание заявки (заявка + части), отмена и перенос выполняются в одной транзакции; согласование — одним `update ... where status='pending'`, отмена — `update ... set cancelled_from=status, status='cancelled' ... where status in ('pending','approved')`. В PostgreSQL создание и перенос сначала блокируют строку сотрудника (`select ... for update`), чтобы две одновременные заявки не прошли проверку остатка по устаревшим данным; в SQLite транзакции и так идут по одной.
**Остаток** не хранится: `accrued(hire_date, date)` минус дни частей заявок на рассмотрении и согласованных; у отменённых после начала согласованных — дни по `cancelled_on` включительно; отменённые до начала и так и не согласованные дни не расходуют. Даты частей при отмене не удаляются (видны в истории). Записи, отменённые до миграции 004 (`cancelled_on` пустой), уже были обрезаны при отмене и учитываются как есть.
**Seed:** 4 пользователя создаются при первом старте. **Миграции:** собственный небольшой механизм вместо Alembic (SQLAlchemy в проекте нет, SQL пишется напрямую): файлы `backend/app/migrations/NNN_имя.sql` применяются при старте по порядку один раз, версии пишутся в `schema_migrations`; одни и те же файлы работают и на PostgreSQL, и на SQLite. `001_init.sql` — исходная схема, `002_notification_read.sql`, `003_sessions.sql`, `004_vacation_audit.sql`. Откатов (down-миграций) нет. Обновление существующей БД с версии 003 на 004 проверено (этап 11).
