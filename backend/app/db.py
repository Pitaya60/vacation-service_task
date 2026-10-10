"""Подключение к PostgreSQL. Без DATABASE_URL поднимает встроенный PostgreSQL 16 (pgserver) в папке .pgdata."""
import hashlib, os, pathlib, secrets
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

ROOT = pathlib.Path(__file__).resolve().parents[2]
DSN: str | None = None
pool: ConnectionPool | None = None
_server = None


def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def check_pw(pw: str, stored: str) -> bool:
    return secrets.compare_digest(hash_pw(pw, stored.split("$")[0]), stored)


def q(sql: str, args=(), c=None):
    if c is None:
        with pool.connection() as cn:
            return q(sql, args, cn)
    cur = c.execute(sql, args)
    return cur.fetchall() if cur.description else []


def init():
    global DSN, pool, _server
    DSN = os.environ.get("DATABASE_URL")
    if not DSN:
        try:  # форк pixeltable-pgserver нужен для Python 3.13+, для 3.9-3.12 подходит и он
            import pixeltable_pgserver as pgserver
        except ImportError:
            try:
                import pgserver
            except ImportError as e:
                raise RuntimeError("Нет пакета pixeltable-pgserver — выполните pip install -r requirements.txt или задайте DATABASE_URL на свой PostgreSQL") from e
        try:
            _server = pgserver.get_server(os.environ.get("PGDATA", str(ROOT / ".pgdata")))
        except Exception as e:
            detail = (getattr(e, "stderr", None) or str(e))[-400:]
            raise RuntimeError(
                "Не удалось запустить встроенный PostgreSQL: " + detail + "\n"
                "Если выше есть 0xC0000135 — не хватает системной DLL: установите Microsoft Visual C++ Redistributable x64 "
                "(https://aka.ms/vs/17/release/vc_redist.x64.exe), удалите папку .pgdata и запустите снова. "
                "Запасной путь: установите обычный PostgreSQL и задайте переменную DATABASE_URL (см. README)."
            ) from e
        DSN = _server.get_uri()
    pool = ConnectionPool(DSN, kwargs={"row_factory": dict_row}, min_size=1, max_size=10, open=True)
    with pool.connection() as c:
        c.execute((pathlib.Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
        if not c.execute("select 1 from users limit 1").fetchone():
            ins = "insert into users(login,pass_hash,name,role,hire_date,team,manager_id) values(%s,%s,%s,%s,%s,%s,%s)"
            c.execute(ins, ("hr", hash_pw("demo"), "Анна (HR)", "hr", "2021-09-01", "HR", None))
            boss = c.execute(ins + " returning id", ("boss", hash_pw("demo"), "Игорь (руководитель)", "manager", "2022-01-10", "Dev", None)).fetchone()["id"]
            c.execute(ins, ("ivan", hash_pw("demo"), "Иван", "employee", "2025-03-01", "Dev", boss))
            c.execute(ins, ("olga", hash_pw("demo"), "Ольга", "employee", "2024-06-15", "Dev", boss))
