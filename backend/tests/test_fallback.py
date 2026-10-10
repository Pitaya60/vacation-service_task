"""Если встроенный PostgreSQL не стартует (как на Windows с 0xC0000135), backend поднимается на запасной SQLite и сообщает об этом."""
import os, subprocess, sys, tempfile, time

import httpx


def test_falls_back_to_sqlite_when_embedded_postgres_fails():
    tmp = tempfile.mkdtemp(prefix="vac_fb_")
    env = {**os.environ, "PGDATA": os.path.join(tmp, "no", "such", "dir", "pg"), "VAC_SQLITE": os.path.join(tmp, "fb.sqlite3")}
    env.pop("DATABASE_URL", None); env.pop("VAC_DB", None)
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8767", "--log-level", "warning"],
                         cwd=os.path.dirname(os.path.dirname(__file__)), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        h = None
        for _ in range(60):
            try:
                h = httpx.get("http://127.0.0.1:8767/api/v1/health").json()
                break
            except Exception:
                time.sleep(0.5)
        assert h and h["status"] == "ok" and h["db"] == "sqlite" and "SQLite" in h["warning"]
        t = httpx.post("http://127.0.0.1:8767/api/v1/login", json={"login": "ivan", "password": "demo"}).json()["token"]
        r = httpx.post("http://127.0.0.1:8767/api/v1/vacations", headers={"Authorization": "Bearer " + t},
                       json={"parts": [{"start": "2027-02-01", "end": "2027-02-14"}]})
        assert r.status_code == 200
    finally:
        p.terminate(); p.wait(10)
