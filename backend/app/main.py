import asyncio, hashlib, logging, os, secrets, threading, time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db, rules
from .rules import plen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vacation")

subs: set[asyncio.Queue] = set()
stopping = threading.Event()  # выставляется при остановке backend, чтобы слушатель не переподключался
SESSION_DAYS = 7
LOGIN_MAX_FAILS = int(os.environ.get("LOGIN_MAX_FAILS", 5))   # неудачных попыток входа на один логин
LOGIN_WINDOW = int(os.environ.get("LOGIN_WINDOW", 300))       # за столько секунд
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173").split(",") if o.strip()]
STATUS_RU = {"pending": "на рассмотрении", "approved": "согласован", "rejected": "отклонён", "cancelled": "отменён"}


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_by_token(token: str):
    """Сессии лежат в БД (хранится хеш токена), поэтому перезапуск backend не разлогинивает."""
    if not token:
        return None
    r = db.q("select user_id, expires_at from sessions where token_hash=%s", (_h(token),))
    if not r or r[0]["expires_at"] < _now():
        return None
    return r[0]["user_id"]


def today() -> date:  # VAC_TODAY нужен только тестам
    v = os.environ.get("VAC_TODAY")
    return date.fromisoformat(v) if v else date.today()


def as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def fmt_parts(parts) -> str:
    """«01.12.2026–14.12.2026 (14 дн.)» — для текстов уведомлений (почта эмулируется, текст должен быть самодостаточным)."""
    ps = sorted((as_date(s), as_date(e)) for s, e in parts)
    days = sum(plen(p) for p in ps)
    return ", ".join(f"{s:%d.%m.%Y}–{e:%d.%m.%Y}" for s, e in ps) + f" ({days} дн.)"


def note(type_: str, vid: int, rid: int | None, text: str):
    """«Ровно одно»: unique(type, vacation_id, recipient_id) + on conflict do nothing. Почта эмулируется строкой в логе."""
    if not rid:
        return
    r = db.q("insert into notifications(type,vacation_id,recipient_id,text) values(%s,%s,%s,%s) on conflict do nothing returning id",
             (type_, vid, rid, text))
    if r:
        log.info("[почта] %s -> user %s: %s", type_, rid, text)


def ping():
    db.notify()


def approvers(u) -> list[int]:
    """Кто согласует заявки сотрудника: его руководитель, а если руководителя нет (руководитель отдела, HR) — другие сотрудники HR."""
    if u["manager_id"]:
        return [u["manager_id"]]
    return [x["id"] for x in db.q("select id from users where role='hr' and id<>%s order by id", (u["id"],))]


def approvers_of(uid: int) -> list[int]:
    return approvers(db.q("select id, manager_id from users where id=%s", (uid,))[0])


def lock_user(c, u):
    """PostgreSQL: блокировка строки сотрудника до конца транзакции, чтобы две одновременные заявки не прошли проверку остатка «вслепую».
    В SQLite транзакции и так выполняются по одной."""
    if db.KIND != "sqlite":
        db.q("select id from users where id=%s for update", (u["id"],), c)


def remind():
    """Напоминание сотруднику и руководителю, когда до начала отпуска осталось не больше REMIND_DAYS дней.
    Условие «не больше», а не «ровно»: если backend не работал в нужный день или заявку согласовали позже, напоминание не теряется.
    Одно на получателя: unique(type, vacation_id, recipient_id) + on conflict do nothing."""
    n = int(os.environ.get("REMIND_DAYS", 3))
    t = today()
    rows = db.q("""select v.id, v.user_id, u.name, (select min(start_date) from vacation_parts where vacation_id=v.id) first_day
        from vacations v join users u on u.id=v.user_id where v.status='approved'
          and (select min(start_date) from vacation_parts where vacation_id=v.id) between %s and %s""",
                (t, t + timedelta(days=n)))
    for r in rows:
        left = (as_date(r["first_day"]) - t).days
        when = "начинается сегодня" if left == 0 else f"начнётся через {left} дн."
        for rid in approvers_of(r["user_id"]):
            note("reminder", r["id"], rid, f"Отпуск сотрудника {r['name']} {when}")
        note("reminder", r["id"], r["user_id"], f"Отпуск {when}")


def _broadcast(loop):
    loop.call_soon_threadsafe(lambda: [s.put_nowait("cal") for s in list(subs)])


def _listen(loop):
    """Слушает NOTIFY. При обрыве соединения (перезапуск БД, сеть) переподключается:
    без этого календари молча переставали бы обновляться до перезапуска backend."""
    while not stopping.is_set():
        try:
            with psycopg.connect(db.DSN, autocommit=True) as c:
                c.execute("listen cal")
                # после переподключения могли пропасть события: пусть клиенты один раз перечитают данные
                _broadcast(loop)
                for _ in c.notifies():
                    _broadcast(loop)
        except Exception as e:
            if stopping.is_set():
                break
            log.warning("[listen] соединение потеряно, повтор через 2 с: %s", e)
        time.sleep(2)


async def _reminders():
    while True:
        try:
            await asyncio.to_thread(remind)
        except Exception:
            log.exception("ошибка фоновой рассылки напоминаний")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_):
    await asyncio.to_thread(db.init)
    loop = asyncio.get_running_loop()
    if db.KIND == "sqlite":
        db.on_notify = lambda: _broadcast(loop)
    else:
        threading.Thread(target=_listen, args=(loop,), daemon=True).start()
    task = asyncio.create_task(_reminders())
    yield
    stopping.set()
    task.cancel()
    db.close()


app = FastAPI(title="Vacation tracker", version="1.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def _http(_, e):
    return JSONResponse({"error": e.detail}, status_code=e.status_code, headers=getattr(e, "headers", None))


@app.exception_handler(RequestValidationError)
async def _val(_, e):
    """Понятный текст вместо технической ошибки pydantic: по имени поля, которое не прошло проверку."""
    fields = {str(x) for err in e.errors() for x in err.get("loc", ())}
    if fields & {"parts", "start", "end"}:
        msg = "Укажите даты начала и окончания каждой части отпуска."
    elif fields & {"login", "password"}:
        msg = "Введите логин и пароль."
    elif "hire_date" in fields:
        msg = "Укажите корректную дату выхода на работу."
    elif "comment" in fields:
        msg = "Комментарий слишком длинный (не больше 500 символов)."
    else:
        msg = "Некорректный запрос: проверьте поля " + ", ".join(sorted(fields - {"body", "query"})) + "."
    return JSONResponse({"error": msg}, status_code=422)


def me(authorization: str = Header(default="")):
    uid = user_by_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Требуется вход")
    return db.q("select * from users where id=%s", (uid,))[0]


class PartIn(BaseModel):
    start: date
    end: date


class VacIn(BaseModel):
    parts: list[PartIn]


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class DecisionIn(BaseModel):
    approve: bool
    comment: str | None = Field(default=None, max_length=500)


class HireIn(BaseModel):
    hire_date: date


api = APIRouter(prefix="/api/v1")


@api.get("/health")
def health():
    return {"status": "ok", "db": db.KIND, "warning": db.warning, "version": app.version}


# --- вход: ограничение неудачных попыток (в памяти процесса; для демо достаточно, для нескольких процессов — Redis/БД) ---
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def _recent_fails(key: str) -> list[float]:
    now = time.monotonic()
    with _fails_lock:
        _fails[key] = [t for t in _fails.get(key, []) if now - t < LOGIN_WINDOW]
        return list(_fails[key])


@api.post("/login")
def login(b: LoginIn):
    key = b.login.strip().lower()
    fails = _recent_fails(key)
    if len(fails) >= LOGIN_MAX_FAILS:
        wait = int(LOGIN_WINDOW - (time.monotonic() - fails[0])) + 1
        raise HTTPException(429, f"Слишком много неудачных попыток входа. Повторите через {wait} с.", headers={"Retry-After": str(wait)})
    u = db.q("select * from users where login=%s", (key,))
    if not u or not db.check_pw(b.password, u[0]["pass_hash"]):
        with _fails_lock:
            _fails.setdefault(key, []).append(time.monotonic())
        raise HTTPException(401, "Неверный логин или пароль")
    with _fails_lock:
        _fails.pop(key, None)
    t = secrets.token_hex(16)
    db.q("delete from sessions where expires_at < %s", (_now(),))  # заодно убираем просроченные сессии
    db.q("insert into sessions(token_hash,user_id,expires_at) values(%s,%s,%s)",
         (_h(t), u[0]["id"], (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()))
    return {"token": t}


@api.post("/logout")
def logout(authorization: str = Header(default="")):
    db.q("delete from sessions where token_hash=%s", (_h(authorization[7:]),))
    return {"ok": True}


@api.get("/me")
def get_me(u=Depends(me)):
    ids = approvers(u)
    names = [r["name"] for r in db.q("select name from users where id in (" + ",".join(["%s"] * len(ids)) + ") order by name", ids)] if ids else []
    return {**{k: v for k, v in u.items() if k != "pass_hash"}, "today": today(), "approvers": names}


def user_parts(uid, c=None) -> list[rules.Part]:
    """Части, которые расходуют остаток: заявки на рассмотрении и согласованные, плюс использованное по отменённым.
    Отменённая до начала или так и не согласованная заявка дни не расходует; отменённая после начала — только по день отмены включительно.
    (Старые отменённые записи без cancelled_on уже были обрезаны при отмене — их части берутся как есть.)"""
    rows = db.q("""select p.start_date s, p.end_date e, v.status, v.cancelled_on, v.cancelled_from from vacation_parts p
                   join vacations v on v.id=p.vacation_id where v.user_id=%s and v.status<>'rejected'""", (uid,), c)
    out = []
    for r in rows:
        s, e = as_date(r["s"]), as_date(r["e"])
        if r["status"] == "cancelled" and r["cancelled_on"]:
            stop = as_date(r["cancelled_on"])
            if r["cancelled_from"] != "approved" or s > stop:
                continue
            e = min(e, stop)
        out.append((s, e))
    return out


def balance_of(hire: date, parts: list[rules.Part], on: date) -> dict:
    used = sum(plen(p) for p in parts if p[0] <= on)
    planned = sum(plen(p) for p in parts if p[0] > on)
    a = rules.accrued(hire, on)
    return {"date": on, "annual": rules.ANNUAL, "accrued": a, "used": used, "reserved": used, "planned": planned,
            "available": a - used, "free": rules.free_days(hire, parts, on)}


@api.get("/balance")
def balance(on_date: date | None = Query(None, alias="date"), u=Depends(me)):
    """accrued — накоплено к дате; used (= reserved, старое имя) — дни частей, начавшихся к дате; planned — дни более поздних заявок;
    available = accrued − used; free — сколько ещё можно запланировать с этой даты с учётом уже поданных заявок."""
    return balance_of(as_date(u["hire_date"]), user_parts(u["id"]), on_date or today())


def create_vacation(c, u, parts, replaces=None):
    if not approvers(u):
        raise HTTPException(422, "Некому согласовать заявку: у вас не назначен руководитель и нет других сотрудников HR.")
    existing = user_parts(u["id"], c)
    err = (rules.validate_parts(parts, today()) or rules.check_balance(as_date(u["hire_date"]), existing, parts)
           or rules.check_year_limit(existing, parts))
    if err:
        raise HTTPException(422, err)
    v = db.q("insert into vacations(user_id,status,replaces_id) values(%s,'pending',%s) returning *", (u["id"], replaces), c)[0]
    for s, e in parts:
        db.q("insert into vacation_parts(vacation_id,start_date,end_date) values(%s,%s,%s)", (v["id"], s, e), c)
    return v


def cancel_vacation(c, v):
    """До начала дни возвращаются целиком; после начала остаётся использованное (по сегодня включительно) — это считает user_parts().
    Даты частей не удаляются, чтобы в истории было видно, какой отпуск отменили.
    Статус меняется атомарным update: два одновременных запроса не отменят и не перенесут заявку дважды."""
    t = today()
    if v["status"] in ("cancelled", "rejected"):
        raise HTTPException(409, "Заявка уже неактивна")
    ps = db.q("select * from vacation_parts where vacation_id=%s", (v["id"],), c)
    if all(as_date(p["end_date"]) < t for p in ps):
        raise HTTPException(409, "Отпуск уже закончился")
    if not db.q("""update vacations set cancelled_from=status, status='cancelled', cancelled_on=%s
                   where id=%s and status in ('pending','approved') returning id""", (t, v["id"]), c):
        raise HTTPException(409, "Заявка уже неактивна")
    return ps


def _parts(b: VacIn):
    return [(p.start, p.end) for p in b.parts]


@api.post("/vacations")
def create(b: VacIn, u=Depends(me)):
    with db.connection() as c:
        lock_user(c, u)
        v = create_vacation(c, u, _parts(b))
    for rid in approvers(u):
        note("new_request", v["id"], rid, f"Новая заявка: {u['name']}, {fmt_parts(_parts(b))}")
    ping()
    return v


def _own(vid, u):
    r = db.q("select * from vacations where id=%s and user_id=%s", (vid, u["id"]))
    if not r:
        raise HTTPException(404, "Не найдено")
    return r[0]


@api.post("/vacations/{vid}/cancel")
def cancel(vid: int, u=Depends(me)):
    v = _own(vid, u)
    with db.connection() as c:
        ps = cancel_vacation(c, v)
    for rid in approvers(u):  # согласующий узнаёт об отмене: он планировал команду с учётом этого отпуска
        note("cancelled", vid, rid, f"{u['name']} отменяет отпуск {fmt_parts([(p['start_date'], p['end_date']) for p in ps])}")
    ping()
    return {"ok": True}


@api.post("/vacations/{vid}/reschedule")
def reschedule(vid: int, b: VacIn, u=Depends(me)):
    """Перенос = атомарно: отмена старой заявки + новая заявка на согласование."""
    old = _own(vid, u)
    with db.connection() as c:
        lock_user(c, u)
        cancel_vacation(c, old)
        v = create_vacation(c, u, _parts(b), old["id"])
    for rid in approvers(u):
        note("new_request", v["id"], rid, f"Перенос отпуска: {u['name']}, новые даты {fmt_parts(_parts(b))} (заявка №{old['id']} отменена)")
    ping()
    return v


@api.post("/vacations/{vid}/decision")
def decision(vid: int, b: DecisionIn, u=Depends(me)):
    r = db.q("select v.*, u.manager_id from vacations v join users u on u.id=v.user_id where v.id=%s", (vid,))
    if not r or u["id"] not in approvers({"id": r[0]["user_id"], "manager_id": r[0]["manager_id"]}):
        raise HTTPException(403, "Это не ваш сотрудник")
    v = r[0]
    comment = (b.comment or "").strip() or None
    if not b.approve and not comment:
        raise HTTPException(422, "При отклонении нужен комментарий")
    done = db.q("""update vacations set status=%s, comment=%s, decided_at=%s, decided_by=%s
                   where id=%s and status='pending' returning id""",
                ("approved" if b.approve else "rejected", comment, _now(), u["id"], vid))
    if not done:
        raise HTTPException(409, "Заявка уже рассмотрена")
    ps = db.q("select start_date, end_date from vacation_parts where vacation_id=%s", (vid,))
    dates = fmt_parts([(p["start_date"], p["end_date"]) for p in ps])
    note("decision", vid, v["user_id"], f"Отпуск {dates} согласован" if b.approve else f"Отпуск {dates} отклонён: {comment}")
    ping()
    return {"ok": True}


@api.get("/vacations")
def vacations(u=Depends(me)):
    """Свои заявки и заявки, которые согласует пользователь: сотрудников команды; для HR ещё и тех, у кого нет руководителя."""
    scope = "(v.user_id=%s or u.manager_id=%s or (%s and u.manager_id is null and u.id<>%s))"
    args = (u["id"], u["id"], u["role"] == "hr", u["id"])
    rows = db.q(f"""select v.id, v.status, v.comment, v.user_id, u.name, u.team, v.created_at, v.decided_at, v.cancelled_on,
                           v.replaces_id, d.name decided_by_name
        from vacations v join users u on u.id=v.user_id left join users d on d.id=v.decided_by
        where {scope} order by v.id desc""", args)
    parts: dict[int, list] = {}
    for p in db.q(f"""select p.vacation_id vid, p.start_date start, p.end_date "end" from vacation_parts p
                     join vacations v on v.id=p.vacation_id join users u on u.id=v.user_id
                     where {scope} order by p.start_date""", args):
        parts.setdefault(p["vid"], []).append({"start": p["start"], "end": p["end"]})
    for r in rows:
        r["parts"] = parts.get(r["id"], [])
        r["days"] = sum(plen((as_date(p["start"]), as_date(p["end"]))) for p in r["parts"])
        if r["user_id"] != u["id"] and r["status"] == "pending":
            r["conflicts"] = db.q("""select distinct u2.name, p2.start_date start, p2.end_date "end" from vacations v2
                join users u2 on u2.id=v2.user_id join vacation_parts p2 on p2.vacation_id=v2.id
                where u2.team=%s and u2.id<>%s and v2.status='approved' and exists(
                  select 1 from vacation_parts p where p.vacation_id=%s and p.start_date<=p2.end_date and p.end_date>=p2.start_date)""",
                                  (r["team"], r["user_id"], r["id"]))
            # сколько у сотрудника останется после согласования: помогает руководителю решить, не открывая HR
            owner = db.q("select hire_date from users where id=%s", (r["user_id"],))[0]
            r["balance_after"] = rules.free_days(as_date(owner["hire_date"]), user_parts(r["user_id"]), today())
    return rows


@api.get("/calendar")
def calendar(scope: str = "team", u=Depends(me)):
    company = scope == "company"
    if company and u["role"] != "hr":
        raise HTTPException(403, "Только HR")
    return db.q("""select v.id, v.status, u.name, u.team, p.start_date start, p.end_date "end" from vacations v
        join users u on u.id=v.user_id join vacation_parts p on p.vacation_id=v.id
        where v.status in('pending','approved') and (%s or u.team=%s) order by p.start_date""", (company, u["team"]))


@api.get("/notifications")
def notifications(u=Depends(me)):
    return db.q("select id,type,vacation_id,text,created_at,read_at from notifications where recipient_id=%s order by id desc limit 30", (u["id"],))


@api.post("/notifications/read")
def notifications_read(u=Depends(me)):
    """Отметить все свои уведомления прочитанными."""
    db.q("update notifications set read_at=%s where recipient_id=%s and read_at is null", (_now(), u["id"]))
    return {"ok": True}


@api.get("/hr/balances")
def hr_balances(u=Depends(me)):
    if u["role"] != "hr":
        raise HTTPException(403, "Только HR")
    t = today()
    out = []
    for x in db.q("""select u.id, u.name, u.team, u.role, u.hire_date, m.name manager
                     from users u left join users m on m.id=u.manager_id order by u.team, u.name"""):
        parts = user_parts(x["id"])
        hire = as_date(x["hire_date"])
        bad = rules.review_balance(hire, parts)
        b = balance_of(hire, parts, t)
        out.append({**x, "accrued": b["accrued"], "available": b["available"], "used": b["used"], "planned": b["planned"],
                    "free": b["free"], "onVacation": any(s <= t <= e for s, e in parts),
                    "needsAttention": bool(bad),
                    "problem": (f"К {bad[0][0][0].isoformat()} накоплено {bad[0][1]} дн., а заявки требуют {bad[0][2]} дн." if bad else None)})
    return out


def review_after_hire_change(uid: int, name: str, manager_id: int | None, hire: date):
    """Пересмотр после смены даты выхода: заявки, которые больше не покрываются накоплением, не отменяются сами,
    но сотрудник, руководитель и HR получают по одному уведомлению на заявку (ключ unique в БД)."""
    rows = db.q("""select v.id vid, p.start_date s, p.end_date e from vacations v join vacation_parts p on p.vacation_id=v.id
                   where v.user_id=%s and v.status in ('pending','approved')""", (uid,))
    owner = {}
    for r in rows:
        owner.setdefault((as_date(r["s"]), as_date(r["e"])), r["vid"])
    hrs = [x["id"] for x in db.q("select id from users where role='hr'")]
    for (s, e), a, need in rules.review_balance(hire, list(owner)):
        vid = owner[(s, e)]
        text = f"Заявка №{vid} ({name}) больше не покрывается накоплением: к {s.isoformat()} накоплено {a} дн., нужно {need} дн. Проверьте заявку."
        for rid in {uid, manager_id, *hrs}:
            note("balance_review", vid, rid, text)


@api.patch("/users/{uid}/hire-date")
def set_hire(uid: int, b: HireIn, u=Depends(me)):
    """Остаток считается функцией, поэтому пересчёт автоматический; конфликтные заявки видны как needsAttention."""
    if u["role"] != "hr":
        raise HTTPException(403, "Только HR")
    if b.hire_date > today():
        raise HTTPException(422, "Дата выхода не может быть в будущем.")
    target = db.q("select * from users where id=%s", (uid,))
    if not target:
        raise HTTPException(404, "Сотрудник не найден")
    db.q("update users set hire_date=%s where id=%s", (b.hire_date, uid))
    review_after_hire_change(target[0]["id"], target[0]["name"], target[0]["manager_id"], b.hire_date)
    ping()
    return {"ok": True}


@api.get("/events")
async def events(token: str):
    if not user_by_token(token):
        raise HTTPException(401, "Требуется вход")
    qq: asyncio.Queue = asyncio.Queue()
    subs.add(qq)

    async def gen():
        try:
            yield "retry: 3000\n\n"  # браузер переподключится через 3 с, если backend перезапустят
            while True:
                try:
                    await asyncio.wait_for(qq.get(), 15)
                    while not qq.empty():  # пачку изменений отдаём одним событием: клиент всё равно перечитывает данные целиком
                        qq.get_nowait()
                    yield "data: cal\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            subs.discard(qq)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.include_router(api)
