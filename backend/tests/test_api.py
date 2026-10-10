"""Интеграционные + e2e тесты: реальная БД и реальный HTTP-сервер uvicorn.
По умолчанию встроенный PostgreSQL во временной папке; `VAC_DB=sqlite pytest` прогоняет те же тесты на запасной SQLite."""
import os, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor

import httpx, pytest, uvicorn

os.environ["PGDATA"] = tempfile.mkdtemp(prefix="vac_pg_")
os.environ["VAC_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="vac_sq_"), "t.sqlite3")
os.environ["REMIND_DAYS"] = "3"
os.environ["VAC_TODAY"] = "2026-10-10"
from app import db, main  # noqa: E402

URL = "http://127.0.0.1:8765/api/v1"
P = lambda a, b: {"start": a, "end": b}


@pytest.fixture(scope="session", autouse=True)
def server():
    srv = uvicorn.Server(uvicorn.Config(main.app, port=8765, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        try:
            if httpx.get(URL + "/health").status_code == 200:
                break
        except Exception:
            time.sleep(0.3)
    yield
    srv.should_exit = True


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
