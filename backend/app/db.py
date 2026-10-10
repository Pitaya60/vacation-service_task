"""Подключение к БД.

Порядок выбора:
1. DATABASE_URL задан -> обычный PostgreSQL (боевой режим).
2. Иначе встроенный PostgreSQL (pixeltable-pgserver, папка .pgdata).
3. Если встроенный не стартовал (например, на Windows 0xC0000135) или VAC_DB=sqlite -> SQLite-файл .vacation.sqlite3.
SQLite нужен только как запасной путь для локального запуска: LISTEN/NOTIFY заменён обратным вызовом в процессе (один процесс backend).
"""
import hashlib, os, pathlib, secrets, sqlite3, threading
from contextlib import contextmanager
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
DSN: str | None = None
KIND = "none"  # postgres | postgres-embedded | sqlite
pool = None
_server = None
_sqlite = None
_lock = threading.RLock()
_depth = 0
on_notify = None  # вызывается в режиме SQLite вместо pg_notify
warning: str | None = None

sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter("date", lambda b: date.fromisoformat(b.decode()))
sqlite3.register_converter("timestamp", lambda b: b.decode())  # без устаревшего конвертера по умолчанию


def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def check_pw(pw: str, stored: str) -> bool:
    return secrets.compare_digest(hash_pw(pw, stored.split("$")[0]), stored)


class _Cur:
    def __init__(self, cur):
        self._c = cur
        self.description = cur.description

    def fetchall(self):
        return [dict(r) for r in self._c.fetchall()]

    def fetchone(self):
        r = self._c.fetchone()
        return dict(r) if r else None


class _SqliteConn:
    """Минимальный аналог соединения psycopg: execute(sql, args) с плейсхолдерами %s."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, args=()):
        return _Cur(self._raw.execute(sql.replace("%s", "?"), tuple(args)))


@contextmanager
def connection():
    """Транзакция: commit при выходе, rollback при исключении (и для PostgreSQL, и для SQLite)."""
    global _depth
    if KIND == "sqlite":
        with _lock:
            if _depth:  # вложенный вызов в той же транзакции
                yield _SqliteConn(_sqlite)
                return
            _depth = 1
            _sqlite.execute("begin")
            try:
                yield _SqliteConn(_sqlite)
                _sqlite.execute("commit")
            except BaseException:
                _sqlite.execute("rollback")
                raise
            finally:
                _depth = 0
    else:
        with pool.connection() as c:
            yield c


def q(sql: str, args=(), c=None):
    if c is None:
        with connection() as cn:
            return q(sql, args, cn)
    cur = c.execute(sql, args)
    return cur.fetchall() if cur.description else []


def notify():
    """Сигнал «календарь изменился»: pg_notify для PostgreSQL, вызов в процессе для SQLite."""
    if KIND == "sqlite":
        if on_notify:
            on_notify()
    else:
        q("select pg_notify('cal','x')")


def reset_data():
    """Очистка заявок и уведомлений (для тестов); пользователи остаются."""
    if KIND == "sqlite":
        with connection() as c:
            for t in ("notifications", "vacation_parts", "vacations"):
                c.execute(f"delete from {t}")
            c.execute("delete from sqlite_sequence where name in ('notifications','vacation_parts','vacations')")
    else:
        q("truncate notifications, vacation_parts, vacations restart identity cascade")


def _start_postgres():
    global _server
    try:  # форк pixeltable-pgserver нужен для Python 3.13+, для 3.9-3.12 подходит и он
        import pixeltable_pgserver as pgserver
    except ImportError:
        import pgserver
    _server = pgserver.get_server(os.environ.get("PGDATA", str(ROOT / ".pgdata")))
    return _server.get_uri()


def _start_sqlite():
    global _sqlite, KIND
    path = os.environ.get("VAC_SQLITE", str(ROOT / ".vacation.sqlite3"))
    _sqlite = sqlite3.connect(path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None)
    _sqlite.row_factory = sqlite3.Row
    _sqlite.execute("pragma foreign_keys=on")
    _sqlite.execute("pragma journal_mode=wal")
    # isolation_level=None: транзакциями управляет connection() (begin/commit/rollback)
    KIND = "sqlite"


def _prepare(sql: str, kind: str) -> str:
    if kind == "sqlite":
        sql = sql.replace("serial primary key", "integer primary key autoincrement").replace("timestamptz default now()", "timestamp default current_timestamp").replace("timestamptz", "timestamp")
    return sql


def _statements(sql: str):
    return [x.strip() for x in sql.split(";") if x.strip()]


def migrate(c, kind: str) -> list[int]:
    """Версионированные миграции: migrations/NNN_имя.sql применяются по порядку, применённые записываются в schema_migrations."""
    c.execute(_prepare("create table if not exists schema_migrations(version integer primary key, name text not null, applied_at timestamptz default now())", kind))
    done = {r["version"] for r in c.execute("select version from schema_migrations").fetchall()}
    for f in sorted((pathlib.Path(__file__).parent / "migrations").glob("*.sql")):
        version = int(f.name.split("_")[0])
        if version in done:
            continue
        for stmt in _statements(_prepare(f.read_text(encoding="utf-8"), kind)):
            c.execute(stmt)
        c.execute("insert into schema_migrations(version,name) values(%s,%s)", (version, f.name))
        done.add(version)
    return sorted(done)


def init():
    global DSN, pool, KIND, warning
    DSN = os.environ.get("DATABASE_URL")
    if os.environ.get("VAC_DB") == "sqlite":
        _start_sqlite()
    elif DSN:
        KIND = "postgres"
    else:
        try:
            DSN = _start_postgres()
            KIND = "postgres-embedded"
        except Exception as e:
            detail = (getattr(e, "stderr", None) or str(e))[-300:]
            warning = ("Встроенный PostgreSQL не запустился (" + detail.strip().splitlines()[-1] + "). "
                       "Работаю на запасной SQLite. Для PostgreSQL установите Visual C++ Redistributable x64 "
                       "(https://aka.ms/vs/17/release/vc_redist.x64.exe) или задайте DATABASE_URL.")
            print("[db] ВНИМАНИЕ:", warning)
            DSN = None
            _start_sqlite()
    if KIND != "sqlite":
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        pool = ConnectionPool(DSN, kwargs={"row_factory": dict_row}, min_size=1, max_size=10, open=True)
    with connection() as c:
        migrate(c, "sqlite" if KIND == "sqlite" else "postgres")
    with connection() as c:
        if not c.execute("select 1 from users limit 1").fetchone():
            ins = "insert into users(login,pass_hash,name,role,hire_date,team,manager_id) values(%s,%s,%s,%s,%s,%s,%s)"
            c.execute(ins, ("hr", hash_pw("demo"), "Анна (HR)", "hr", date(2021, 9, 1), "HR", None))
            boss = c.execute(ins + " returning id", ("boss", hash_pw("demo"), "Игорь (руководитель)", "manager", date(2022, 1, 10), "Dev", None)).fetchone()["id"]
            c.execute(ins, ("ivan", hash_pw("demo"), "Иван", "employee", date(2025, 3, 1), "Dev", boss))
            c.execute(ins, ("olga", hash_pw("demo"), "Ольга", "employee", date(2024, 6, 15), "Dev", boss))
