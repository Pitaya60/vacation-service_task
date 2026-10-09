# Database Design (PostgreSQL 16)

- `users(id, login unique, pass_hash, name, role in employee|manager|hr, hire_date, team, manager_id → users)`
- `vacations(id, user_id → users, status in pending|approved|rejected|cancelled, comment, replaces_id → vacations, created_at)`
- `vacation_parts(id, vacation_id → vacations on delete cascade, start_date, end_date, check end>=start)` — части отпуска; индекс по vacation_id.
- `notifications(id, type, vacation_id, recipient_id, text, created_at, unique(type, vacation_id, recipient_id))` — уникальный ключ = «ровно одно».

**Целостность:** внешние ключи, check на роли и статусы, check дат, unique на логин и уведомления.
**Транзакции:** создание заявки (заявка + части), отмена и перенос выполняются в одной транзакции; согласование — одним `update ... where status='pending'`.
**Остаток** не хранится: `accrued(hire_date, date)` минус дни частей не отклонённых заявок. Отменённые после начала заявки сохраняют использованные части.
**Seed:** 4 пользователя создаются при первом старте. **Миграции:** Alembic не используется, схема применяется `schema.sql` (`create ... if not exists`).
