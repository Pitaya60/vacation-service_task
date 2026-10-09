# Test Plan и результаты

Запуск: `cd backend; python -m pytest -v`. Тесты поднимают временный PostgreSQL и HTTP-сервер сами.

| ID | Проверка | Тест | Результат |
|---|---|---|---|
| T01 | Начисление 28 дн./год, 0 до выхода, пересчёт при смене даты | test_rules.py::test_accrual_*, test_hire_date_change_recalculates | Pass (сессия Claude) |
| T02 | Правила дробления (нет 14 дн., часть <5, >3 частей, пересечение, задним числом) | test_rules.py, test_split_rule_message | Pass (сессия Claude) |
| T03 | Заявка сверх накопленного отклоняется | test_over_balance_rejected | Pass (сессия Claude) |
| T04 | Уведомления ровно по одному, гонка двух согласований | test_notifications_exactly_once_and_race | Pass (сессия Claude) |
| T05 | Отклонение требует комментария | test_reject_needs_comment | Pass (сессия Claude) |
| T06 | Руководитель видит конфликт с согласованным отпуском | test_manager_sees_conflict | Pass (сессия Claude) |
| T07 | Отмена до начала возвращает все дни; после начала — только неиспользованные | test_cancel_* | Pass (сессия Claude) |
| T08 | Перенос атомарен | test_reschedule_is_atomic | Pass (сессия Claude) |
| T09 | Напоминание ровно одно, обоим | test_reminder_exactly_once_for_both | Pass (сессия Claude) |
| T10 | Календарь компании только для HR; нет входа — 401 | test_company_calendar_hr_only, test_requires_auth | Pass (сессия Claude) |
| T11 | Две сессии: действие одной приходит другой по SSE | test_sse_two_sessions | Pass (сессия Claude) |
| T12 | Свежий запуск на вашем компьютере (`start.ps1`) | вручную | **Не выполнено — заполнить** |
| T13 | Две вкладки браузера вручную (ivan + boss) | вручную | **Не выполнено — заполнить** |
| T14 | Перезапуск backend, данные сохранились | вручную (.pgdata) | **Не выполнено — заполнить** |

Результат «Pass (сессия Claude)» получен в среде Claude: Linux, Python 3.12, 27 passed. Для сдачи сохраните свой вывод: `python -m pytest -v > ..\TEST_RESULTS.txt`.
Не покрыто тестами: поведение интерфейса, недоступность backend во frontend, ограничения БД напрямую.
