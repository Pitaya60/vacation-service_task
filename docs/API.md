# API Design — `/api/v1`, HTTP/JSON, интерактивная документация на http://localhost:8000/docs

Авторизация: `Authorization: Bearer <token>` из `POST /login`. Ошибки: `{"error": "текст"}`.

| Метод и путь | Назначение | Ошибки |
|---|---|---|
| POST /login | вход | 401 |
| GET /me, GET /balance?date= | профиль; накоплено/зарезервировано/доступно на дату | 401 |
| POST /vacations `{parts:[{start,end}]}` | заявка | 422 правила, 401 |
| POST /vacations/{id}/cancel | отмена | 404, 409 |
| POST /vacations/{id}/reschedule | перенос (атомарно) | 404, 409, 422 |
| POST /vacations/{id}/decision `{approve, comment}` | согласование | 403, 409 уже рассмотрена, 422 нет комментария |
| GET /vacations | свои заявки и заявки подчинённых (с `conflicts`) | |
| GET /calendar?scope=team\|company | календарь (company только HR) | 403 |
| GET /notifications | уведомления пользователя | |
| GET /hr/balances, PATCH /users/{id}/hire-date | остатки; смена даты выхода (HR) | 403 |
| GET /events?token= | SSE: событие `cal` при любом изменении | 401 |

**Между клиентами:** изменение → `pg_notify('cal')` → SSE всем подключённым → клиент перечитывает данные. **Дубли:** уникальный ключ уведомлений; параллельные решения — 409.
