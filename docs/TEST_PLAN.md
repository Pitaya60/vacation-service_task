# Test Plan и результаты

Запуск: `cd backend; python -m pytest -v`. Тесты поднимают временный PostgreSQL и HTTP-сервер сами. Те же проверки GitHub выполняет при каждом push (`.github/workflows/ci.yml`: backend на PostgreSQL и SQLite, сборка frontend).

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
| T17 | Годовой лимит: не больше 4 частей в календарном году, другой год считается отдельно | test_rules.py::test_year_limit_*, test_year_limit_via_api | Pass (сессия Claude) |
| T18 | Смена даты выхода: заявки, не покрытые накоплением, дают по одному уведомлению сотруднику, руководителю и HR; без конфликта уведомлений нет; 403 и 404 | test_hire_change_* | Pass (сессия Claude) |
| T19 | Уведомления: `read_at`, новое снова непрочитано | test_notifications_read_flag | Pass (сессия Claude) |
| T20 | Сессии в БД: хеш токена, выход, просрочка | test_sessions_live_in_db_and_logout_works | Pass (сессия Claude); реальный перезапуск процесса вручную не проверялся |
| T21 | Миграции применяются один раз, повторный запуск ничего не меняет | test_migrations_recorded_once | Pass (сессия Claude) |
| T22 | Интерфейс в Chromium: ошибка в форме, заявка → руководитель без перезагрузки, отказ с причиной, правка даты выхода у HR, счётчик уведомлений, мобильная ширина | e2e/test_ui.py | Pass: 5 passed, дважды подряд (сессия Claude, `E2E_RESULTS.txt`) |
| T23 | Обрыв соединения LISTEN: после переподключения SSE снова доставляет события | test_sse_survives_listener_connection_drop | Pass на PostgreSQL (сессия Claude); до исправления падал; на SQLite пропущен |
| T24 | Руководитель без руководителя (boss): заявку согласует HR, уведомление приходит HR, сам себе и чужие сотрудники не согласуют | test_manager_without_manager_is_approved_by_hr, test_hr_cannot_approve_requests_of_people_who_have_a_manager | Pass (сессия Claude); до исправления падал |
| T25 | Некому согласовать (HR без руководителя): понятная ошибка 422, заявка не создаётся | test_request_with_nobody_to_approve_is_refused_clearly | Pass (сессия Claude); до исправления падал |
| T26 | Напоминание не теряется: согласовано за 2 дня при REMIND_DAYS=3, повторный запуск ничего не добавляет; далёкие, начавшиеся и несогласованные отпуска не напоминают | test_reminder_catches_up_*, test_no_reminder_for_far_or_started_vacations | Pass (сессия Claude); первый до исправления падал |
| T27 | Две одновременные заявки одного сотрудника не обходят проверку остатка (ровно одна проходит) | test_concurrent_requests_cannot_overspend_balance | Pass на PostgreSQL (сессия Claude, 6 прогонов подряд); до исправления падал; на SQLite гонки нет |
| T15 | Те же тесты на запасной SQLite (`VAC_DB=sqlite`) | весь test_api.py | Pass: 43 passed, 1 skipped (сессия Claude) |
| T16 | Сбой встроенного PostgreSQL → автоматический переход на SQLite, `/health` показывает `sqlite` и предупреждение, заявка создаётся | test_fallback.py | Pass (сессия Claude, сбой смоделирован неверным `PGDATA`; реальный сбой на Windows этим не воспроизведён) |
| T12 | Свежий запуск на вашем компьютере (`start.bat`) | вручную | **Не выполнено — заполнить** |
| T13 | Две вкладки браузера вручную (ivan + boss) | вручную | **Не выполнено — заполнить** |
| T14 | Перезапуск backend, данные сохранились | вручную (.pgdata) | **Не выполнено — заполнить** |

Результат «Pass (сессия Claude)» получен в среде Claude: Linux, Python 3.12, 44 passed на PostgreSQL 18.4 и 43 passed + 1 skipped на SQLite (вывод в `TEST_RESULTS.txt`); сквозные тесты интерфейса — `E2E_RESULTS.txt`. Для сдачи сохраните свой вывод: `python -m pytest -v > ..\TEST_RESULTS.txt`.
Не покрыто тестами: недоступность backend во frontend, ограничения БД напрямую, другие браузеры, Windows.
