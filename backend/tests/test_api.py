"""Интеграционные + e2e тесты: реальная БД и реальный HTTP-сервер uvicorn.
По умолчанию встроенный PostgreSQL во временной папке; `VAC_DB=sqlite pytest` прогоняет те же тесты на запасной SQLite."""
import os, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx, pytest, uvicorn

os.environ["PGDATA"] = tempfile.mkdtemp(prefix="vac_pg_")
os.environ["VAC_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="vac_sq_"), "t.sqlite3")
os.environ["REMIND_DAYS"] = "3"
os.environ["VAC_TODAY"] = "2026-10-10"
from app import db, main, rules  # noqa: E402

URL = "http://127.0.0.1:8765/api/v1"
P = lambda a, b: {"start": a, "end": b}


@pytest.fixture(scope="session", autouse=True)
def server():
    srv = uvicorn.Server(uvicorn.Config(main.app, port=8765, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            if httpx.get(URL + "/health").status_code == 200:
                break
        except Exception:
            time.sleep(0.3)
    yield
    srv.should_exit = True
    th.join(10)  # штатная остановка: lifespan выставит stopping, слушатель выйдет без сообщений


@pytest.fixture(autouse=True)
def clean():
    os.environ["VAC_TODAY"] = "2026-10-10"
    db.reset_data()
    db.q("update users set hire_date='2025-03-01' where login='ivan'")


def tok(u):
    return httpx.post(URL + "/login", json={"login": u, "password": "demo"}).json()["token"]


def call(t, path, m="GET", body=None):
    r = httpx.request(m, URL + path, headers={"Authorization": "Bearer " + t}, json=body)
    return r.status_code, r.json()


def notes(t, vid, typ):
    return [n for n in call(t, "/notifications")[1] if n["vacation_id"] == vid and n["type"] == typ]


def test_health_reports_db():
    h = httpx.get(URL + "/health").json()
    assert h["status"] == "ok" and h["db"] == ("sqlite" if os.environ.get("VAC_DB") == "sqlite" else "postgres-embedded")

def test_wrong_password():
    assert httpx.post(URL + "/login", json={"login": "ivan", "password": "x"}).status_code == 401

def test_requires_auth():
    assert httpx.get(URL + "/me").status_code == 401

def test_over_balance_rejected():
    s, b = call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-10-20", "2026-11-02")]})
    assert s == 200  # к этой дате накоплено достаточно
    s, b = call(tok("olga"), "/vacations", "POST", {"parts": [P("2024-07-01", "2024-07-14")]})
    assert s == 422  # задним числом
    db.q("update users set hire_date='2026-09-01' where login='ivan'")
    s, b = call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert s == 422 and "накоплено" in b["error"]

def test_split_rule_message():
    s, b = call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-07")]})
    assert s == 422 and b["error"] == "В заявке нет части от 14 дней."

def test_forecast_grows_with_date():
    t = tok("ivan")
    assert call(t, "/balance?date=2027-06-01")[1]["accrued"] > call(t, "/balance?date=2026-06-01")[1]["accrued"]

def test_notifications_exactly_once_and_race():
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    assert len(notes(bo, vid, "new_request")) == 1
    with ThreadPoolExecutor(2) as ex:
        codes = sorted(f.result()[0] for f in [ex.submit(call, bo, f"/vacations/{vid}/decision", "POST", {"approve": True}) for _ in range(2)])
    assert codes == [200, 409]
    assert len(notes(iv, vid, "decision")) == 1

def test_reject_needs_comment():
    vid = call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    assert call(tok("boss"), f"/vacations/{vid}/decision", "POST", {"approve": False})[0] == 422
    assert call(tok("boss"), f"/vacations/{vid}/decision", "POST", {"approve": False, "comment": "Релиз"})[0] == 200

def test_manager_sees_conflict():
    iv, ol, bo = tok("ivan"), tok("olga"), tok("boss")
    a = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    call(bo, f"/vacations/{a}/decision", "POST", {"approve": True})
    b = call(ol, "/vacations", "POST", {"parts": [P("2026-12-05", "2026-12-18")]})[1]["id"]
    row = next(v for v in call(bo, "/vacations")[1] if v["id"] == b)
    assert row["conflicts"] and row["conflicts"][0]["name"] == "Иван"

def test_cancel_before_start_returns_all_days():
    iv = tok("ivan")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    assert call(iv, "/balance?date=2027-01-01")[1]["reserved"] == 14
    assert call(iv, f"/vacations/{vid}/cancel", "POST")[0] == 200
    assert call(iv, "/balance?date=2027-01-01")[1]["reserved"] == 0

def test_cancel_after_start_returns_only_unused():
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-10-20", "2026-11-02")]})[1]["id"]
    call(bo, f"/vacations/{vid}/decision", "POST", {"approve": True})
    os.environ["VAC_TODAY"] = "2026-10-25"  # отпуск начался 20-го; использовано 20..25 = 6 дней
    assert call(iv, f"/vacations/{vid}/cancel", "POST")[0] == 200
    assert call(iv, "/balance?date=2027-01-01")[1]["reserved"] == 6

def test_reschedule_is_atomic():
    iv = tok("ivan")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    s, _ = call(iv, f"/vacations/{vid}/reschedule", "POST", {"parts": [P("2026-12-01", "2026-12-03")]})
    assert s == 422  # новая заявка невалидна -> старая не отменена
    assert next(v for v in call(iv, "/vacations")[1] if v["id"] == vid)["status"] == "pending"
    assert call(iv, f"/vacations/{vid}/reschedule", "POST", {"parts": [P("2027-01-11", "2027-01-24")]})[0] == 200

def test_reminder_exactly_once_for_both():
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-10-13", "2026-10-26")]})[1]["id"]
    call(bo, f"/vacations/{vid}/decision", "POST", {"approve": True})
    main.remind(); main.remind()
    assert len(notes(iv, vid, "reminder")) == 1 and len(notes(bo, vid, "reminder")) == 1

def test_reminder_catches_up_when_approved_late_or_missed_day():
    """Согласовали за 2 дня до начала при REMIND_DAYS=3, или backend не работал ровно в «день X»: напоминание всё равно приходит, один раз."""
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-10-12", "2026-10-25")]})[1]["id"]
    call(bo, f"/vacations/{vid}/decision", "POST", {"approve": True})
    main.remind(); main.remind()
    n = notes(iv, vid, "reminder")
    assert len(n) == 1 and "через 2 дн." in n[0]["text"] and len(notes(bo, vid, "reminder")) == 1


def test_no_reminder_for_far_or_started_vacations():
    iv, bo = tok("ivan"), tok("boss")
    far = call(iv, "/vacations", "POST", {"parts": [P("2026-11-02", "2026-11-15")]})[1]["id"]
    call(bo, f"/vacations/{far}/decision", "POST", {"approve": True})
    pending = call(iv, "/vacations", "POST", {"parts": [P("2026-10-12", "2026-10-25")]})[1]["id"]  # не согласована
    main.remind()
    assert not notes(iv, far, "reminder") and not notes(iv, pending, "reminder")
    os.environ["VAC_TODAY"] = "2026-11-05"  # далёкий отпуск уже идёт: «напоминать» поздно
    main.remind()
    assert not notes(iv, far, "reminder")


def test_manager_without_manager_is_approved_by_hr():
    bo, hr, iv = tok("boss"), tok("hr"), tok("ivan")
    s, v = call(bo, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert s == 200
    assert len(notes(hr, v["id"], "new_request")) == 1                      # HR получил уведомление
    assert any(x["id"] == v["id"] for x in call(hr, "/vacations")[1])        # и видит заявку
    assert call(iv, f"/vacations/{v['id']}/decision", "POST", {"approve": True})[0] == 403  # чужой сотрудник не согласует
    assert call(bo, f"/vacations/{v['id']}/decision", "POST", {"approve": True})[0] == 403  # и сам себе тоже
    assert call(hr, f"/vacations/{v['id']}/decision", "POST", {"approve": True})[0] == 200
    assert len(notes(bo, v["id"], "decision")) == 1


def test_hr_cannot_approve_requests_of_people_who_have_a_manager():
    iv, hr = tok("ivan"), tok("hr")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    assert call(hr, f"/vacations/{vid}/decision", "POST", {"approve": True})[0] == 403
    assert not any(x["id"] == vid for x in call(hr, "/vacations")[1])


def test_request_with_nobody_to_approve_is_refused_clearly():
    s, b = call(tok("hr"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert s == 422 and "Некому согласовать" in b["error"]


def test_concurrent_requests_cannot_overspend_balance():
    """Два одновременных запроса одного сотрудника не должны оба пройти проверку остатка."""
    assert rules.accrued(date(2026, 6, 1), date(2026, 12, 1)) == 14 and rules.accrued(date(2026, 6, 1), date(2026, 12, 20)) == 15
    db.q("update users set hire_date='2026-06-01' where login='ivan'")
    iv = tok("ivan")
    barrier = threading.Barrier(2)
    def send(a, b):
        barrier.wait()
        return call(iv, "/vacations", "POST", {"parts": [P(a, b)]})[0]
    with ThreadPoolExecutor(2) as ex:
        codes = sorted(f.result() for f in [ex.submit(send, "2026-12-01", "2026-12-14"), ex.submit(send, "2026-12-20", "2027-01-02")])
    assert codes == [200, 422]


def test_hire_date_change_recalculates():
    iv, hr = tok("ivan"), tok("hr")
    before = call(iv, "/balance?date=2026-10-10")[1]["accrued"]
    assert call(hr, "/users/3/hire-date", "PATCH", {"hire_date": "2026-01-01"})[0] == 200
    assert call(iv, "/balance?date=2026-10-10")[1]["accrued"] < before

def test_company_calendar_hr_only():
    assert call(tok("ivan"), "/calendar?scope=company")[0] == 403
    assert call(tok("hr"), "/calendar?scope=company")[0] == 200

def test_sse_two_sessions():
    got = threading.Event()
    bo = tok("boss")
    def listen():
        with httpx.stream("GET", URL + "/events", params={"token": bo}, timeout=15) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    got.set(); return
    threading.Thread(target=listen, daemon=True).start()
    time.sleep(1)
    call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert got.wait(5), "боксу не пришло событие по SSE"


@pytest.mark.skipif(os.environ.get("VAC_DB") == "sqlite", reason="LISTEN/NOTIFY есть только в PostgreSQL")
def test_sse_survives_listener_connection_drop():
    """Обрыв соединения LISTEN (перезапуск БД, сеть) не должен навсегда отключать обновления без перезагрузки."""
    bo = tok("boss")
    time.sleep(1)
    db.q("select pg_terminate_backend(pid) from pg_stat_activity where query ilike 'listen cal%%' and pid <> pg_backend_pid()")
    got = threading.Event()
    def listen():
        with httpx.stream("GET", URL + "/events", params={"token": bo}, timeout=20) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    got.set(); return
    threading.Thread(target=listen, daemon=True).start()
    time.sleep(3)  # даём слушателю переподключиться
    call(tok("ivan"), "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert got.wait(5), "после обрыва соединения событие по SSE больше не приходит"


def test_year_limit_via_api():
    iv = tok("ivan")
    ok = lambda parts: call(iv, "/vacations", "POST", {"parts": parts})
    assert ok([P("2027-02-01", "2027-02-14"), P("2027-03-01", "2027-03-05"), P("2027-04-01", "2027-04-05")])[0] == 200
    assert ok([P("2027-05-03", "2027-05-16")])[0] == 200                       # четвёртая часть в 2027
    s, b = ok([P("2027-06-01", "2027-06-14")])
    assert s == 422 and "больше 4 частей в год" in b["error"]                  # пятая не проходит, текст понятный
    assert ok([P("2028-01-10", "2028-01-23")])[0] == 200                       # другой год — свой лимит


def test_hire_change_review_notifies_once_each():
    iv, bo, hr = tok("ivan"), tok("boss"), tok("hr")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-28")]})[1]["id"]
    assert call(hr, "/users/3/hire-date", "PATCH", {"hire_date": "2026-06-01"})[0] == 200
    call(hr, "/users/3/hire-date", "PATCH", {"hire_date": "2026-06-01"})          # повтор не плодит уведомления
    for t in (iv, bo, hr):
        assert len(notes(t, vid, "balance_review")) == 1
    row = [u for u in call(hr, "/hr/balances")[1] if u["id"] == 3][0]
    assert row["needsAttention"] and "накоплено 14" in row["problem"]
    assert call(hr, "/users/999/hire-date", "PATCH", {"hire_date": "2026-06-01"})[0] == 404
    assert call(iv, "/users/3/hire-date", "PATCH", {"hire_date": "2026-06-01"})[0] == 403


def test_hire_change_without_conflict_sends_nothing():
    iv, hr = tok("ivan"), tok("hr")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    call(hr, "/users/3/hire-date", "PATCH", {"hire_date": "2025-01-01"})
    assert notes(iv, vid, "balance_review") == []


def test_notifications_read_flag():
    iv, bo = tok("ivan"), tok("boss")
    call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})
    assert [n["read_at"] for n in call(bo, "/notifications")[1]] == [None]
    assert call(bo, "/notifications/read", "POST")[0] == 200
    assert all(n["read_at"] for n in call(bo, "/notifications")[1])
    call(iv, "/vacations", "POST", {"parts": [P("2027-02-01", "2027-02-14")]})
    assert [bool(n["read_at"]) for n in call(bo, "/notifications")[1]] == [False, True]   # новое снова непрочитано


def test_sessions_live_in_db_and_logout_works():
    import hashlib
    t = tok("ivan")
    hashes = [r["token_hash"] for r in db.q("select token_hash from sessions")]
    assert hashlib.sha256(t.encode()).hexdigest() in hashes and t not in hashes   # токен в открытом виде не хранится
    assert call(t, "/me")[0] == 200
    assert call(t, "/logout", "POST")[0] == 200
    assert call(t, "/me")[0] == 401
    t2 = tok("ivan")
    db.q("update sessions set expires_at='2000-01-01T00:00:00+00:00'")
    assert call(t2, "/me")[0] == 401                                              # просроченная сессия не работает


def test_migrations_recorded_once():
    assert [r["version"] for r in db.q("select version from schema_migrations order by version")] == [1, 2, 3, 4]
    with db.connection() as c:
        assert db.migrate(c, "sqlite" if db.KIND == "sqlite" else "postgres") == [1, 2, 3, 4]   # повторный запуск ничего не меняет


# --- доработки backend, этап 11 ---

def test_balance_free_accounts_for_future_requests():
    """«Доступно» без учёта будущих заявок вводило в заблуждение: free показывает, сколько реально можно ещё запланировать."""
    iv = tok("ivan")
    b0 = call(iv, "/balance")[1]
    assert b0["accrued"] == 45 and b0["free"] == 45 and b0["planned"] == 0
    call(iv, "/vacations", "POST", {"parts": [P("2026-10-20", "2026-11-02")]})
    b1 = call(iv, "/balance")[1]
    assert b1["planned"] == 14 and b1["used"] == 0 and b1["available"] == 45 and b1["free"] == 31
    # free с даты — ровно столько, сколько пропустит проверка заявки с началом в эту дату: f+1 дней нельзя, f можно
    f = call(iv, "/balance?date=2026-11-03")[1]["free"]
    assert f == 32
    end = lambda n: (date(2026, 11, 3) + timedelta(days=n - 1)).isoformat()
    assert call(iv, "/vacations", "POST", {"parts": [P("2026-11-03", end(f + 1))]})[0] == 422
    assert call(iv, "/vacations", "POST", {"parts": [P("2026-11-03", end(f))]})[0] == 200


def test_cancel_keeps_dates_and_notifies_approver_once():
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    assert call(iv, f"/vacations/{vid}/cancel", "POST")[0] == 200
    row = next(v for v in call(iv, "/vacations")[1] if v["id"] == vid)
    assert row["status"] == "cancelled" and row["parts"] == [P("2026-12-01", "2026-12-14")] and row["cancelled_on"] == "2026-10-10"
    n = notes(bo, vid, "cancelled")
    assert len(n) == 1 and "01.12.2026–14.12.2026" in n[0]["text"]
    assert call(iv, f"/vacations/{vid}/cancel", "POST")[0] == 409
    assert call(iv, "/balance?date=2027-01-01")[1]["used"] == 0


def test_cancelled_pending_after_its_start_returns_all_days():
    """Заявку так и не согласовали, дата начала прошла, сотрудник её отменил: в отпуске он не был, дни возвращаются целиком."""
    iv = tok("ivan")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-10-20", "2026-11-02")]})[1]["id"]
    os.environ["VAC_TODAY"] = "2026-10-25"
    assert call(iv, f"/vacations/{vid}/cancel", "POST")[0] == 200
    assert call(iv, "/balance?date=2027-01-01")[1]["used"] == 0


def test_decision_records_who_and_when():
    iv, bo = tok("ivan"), tok("boss")
    vid = call(iv, "/vacations", "POST", {"parts": [P("2026-12-01", "2026-12-14")]})[1]["id"]
    pending = next(v for v in call(bo, "/vacations")[1] if v["id"] == vid)
    assert pending["balance_after"] == 35 and pending["days"] == 14     # руководитель видит остаток сотрудника
    call(bo, f"/vacations/{vid}/decision", "POST", {"approve": True, "comment": "  "})
    row = next(v for v in call(iv, "/vacations")[1] if v["id"] == vid)
    assert row["decided_by_name"].startswith("Игорь") and row["decided_at"] and row["comment"] is None
    assert "01.12.2026–14.12.2026" in notes(iv, vid, "decision")[0]["text"]


def test_me_names_who_approves():
    assert call(tok("ivan"), "/me")[1]["approvers"] == ["Игорь (руководитель)"]
    assert call(tok("boss"), "/me")[1]["approvers"] == ["Анна (HR)"]
    assert call(tok("hr"), "/me")[1]["approvers"] == []


def test_login_is_throttled_after_repeated_failures():
    for _ in range(main.LOGIN_MAX_FAILS):
        assert httpx.post(URL + "/login", json={"login": "ghost", "password": "x"}).status_code == 401
    r = httpx.post(URL + "/login", json={"login": "Ghost", "password": "x"})
    assert r.status_code == 429 and "Повторите через" in r.json()["error"] and int(r.headers["Retry-After"]) > 0
    assert httpx.post(URL + "/login", json={"login": "olga", "password": "demo"}).status_code == 200   # другие логины не задеты


def test_validation_errors_are_human_readable():
    iv = tok("ivan")
    s, b = call(iv, "/vacations", "POST", {"parts": [{"start": "2026-12-01"}]})
    assert s == 422 and b["error"] == "Укажите даты начала и окончания каждой части отпуска."
    r = httpx.post(URL + "/login", json={"login": ""})
    assert r.status_code == 422 and r.json()["error"] == "Введите логин и пароль."
    assert call(tok("hr"), "/users/3/hire-date", "PATCH", {"hire_date": "2030-01-01"})[0] == 422   # дата выхода в будущем


def test_expired_sessions_are_purged_on_login():
    t = tok("olga")
    db.q("update sessions set expires_at='2000-01-01T00:00:00+00:00' where token_hash=%s", (main._h(t),))
    tok("olga")
    assert not db.q("select 1 from sessions where expires_at < '2001-01-01'")
