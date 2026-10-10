# API Design — `/api/v1`, HTTP/JSON, интерактивная документация на http://localhost:8000/docs

Авторизация: `Authorization: Bearer <token>` из `POST /login`. Ошибки: `{"error": "текст"}`.

| Метод и путь | Назначение | Ошибки |
|---|---|---|
| GET /health | `{status, db, warning}`: какая БД работает (`postgres-embedded`, `postgres`, `sqlite`) | |
| POST /login, POST /logout | вход (токен хранится в БД в виде хеша, срок 7 дней); выход | 401 |
| GET /me, GET /balance?date= | профиль; накоплено/зарезервировано/доступно на дату | 401 |
| POST /vacations `{parts:[{start,end}]}` | заявка | 422 правила (в том числе не больше 4 частей в календарном году), 401 |
| POST /vacations/{id}/cancel | отмена | 404, 409 |
| POST /vacations/{id}/reschedule | перенос (атомарно) | 404, 409, 422 |
| POST /vacations/{id}/decision `{approve, comment}` | согласование | 403, 409 уже рассмотрена, 422 нет комментария |
| GET /vacations | свои заявки и заявки подчинённых (с `conflicts`) | |
| GET /calendar?scope=team\|company | календарь (company только HR) | 403 |
| GET /notifications, POST /notifications/read | уведомления пользователя (с `read_at`); отметить все прочитанными | |
| GET /hr/balances, PATCH /users/{id}/hire-date | остатки (`needsAttention`, `problem`); смена даты выхода (HR), после неё уведомления по заявкам, которые перестали покрываться накоплением | 403, 404 |
| GET /events?token= | SSE: событие `cal` при любом изменении | 401 |

**Между клиентами:** изменение → `pg_notify('cal')` (в режиме SQLite — вызов в процессе) → SSE всем подключённым → клиент перечитывает данные. **Дубли:** уникальный ключ уведомлений; параллельные решения — 409.
