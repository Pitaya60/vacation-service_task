import asyncio, hashlib, os, secrets, threading, time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import db, rules
from .rules import plen

subs: set[asyncio.Queue] = set()
stopping = threading.Event()  # выставляется при остановке backend, чтобы слушатель не переподключался
SESSION_DAYS = 7


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_by_token(token: str):
    """Сессии лежат в БД (хранится хеш токена), поэтому перезапуск backend не разлогинивает."""
    if not token:
        return None
    r = db.q("select user_id, expires_at from sessions where token_hash=%s", (_h(token),))
    if not r or r[0]["expires_at"] < datetime.now(timezone.utc).isoformat():
        return None
    return r[0]["user_id"]


def today() -> date:  # VAC_TODAY нужен только тестам
    v = os.environ.get("VAC_TODAY")
    return date.fromisoformat(v) if v else date.today()


def note(type_: str, vid: int, rid: int | None, text: str):
    """«Ровно одно»: unique(type, vacation_id, recipient_id) + on conflict do nothing."""
    if not rid:
        return
    r = db.q("insert into notifications(type,vacation_id,recipient_id,text) values(%s,%s,%s,%s) on conflict do nothing returning id",
             (type_, vid, rid, text))
    if r:
        print(f"[notify] {type_} -> user {rid}: {text}")


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
    rows = db.q("""select v.id, v.user_id, (select min(start_date) from vacation_parts where vacation_id=v.id) first_day
        from vacations v where v.status='approved'
          and (select min(start_date) from vacation_parts where vacation_id=v.id) between %s and %s""",
                (t, t + timedelta(days=n)))
    for r in rows:
        left = (date.fromisoformat(str(r["first_day"])) - t).days
        text = "Отпуск начинается сегодня." if left == 0 else f"Отпуск начнётся через {left} дн."
        for rid in approvers_of(r["user_id"]) + [r["user_id"]]:
            note("reminder", r["id"], rid, text)


def _listen(loop):
    """Слушает NOTIFY. При обрыве соединения (перезапуск БД, сеть) переподключается:
    без этого календари молча переставали бы обновляться до перезапуска backend."""
    while not stopping.is_set():
        try:
            with psycopg.connect(db.DSN, autocommit=True) as c:
                c.execute("listen cal")
                # после переподключения могли пропасть события: пусть клиенты один раз перечитают данные
                loop.call_soon_threadsafe(lambda: [s.put_nowait("cal") for s in list(subs)])
                for _ in c.notifies():
                    loop.call_soon_threadsafe(lambda: [s.put_nowait("cal") for s in list(subs)])
        except Exception as e:
            if stopping.is_set():
                break
            print("[listen] соединение потеряно, повтор через 2 с:", e)
        time.sleep(2)


async def _reminders():
    while True:
        try:
            await asyncio.to_thread(remind)
        except Exception as e:
            print("remind error", e)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_):
    await asyncio.to_thread(db.init)
    loop = asyncio.get_running_loop()
    if db.KIND == "sqlite":
        db.on_notify = lambda: loop.call_soon_threadsafe(lambda: [s.put_nowait("cal") for s in list(subs)])
    else:
        threading.Thread(target=_listen, args=(loop,), daemon=True).start()
    task = asyncio.create_task(_reminders())
    yield
    stopping.set()
    task.cancel()


app = FastAPI(title="Vacation tracker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def _http(_, e):
    return JSONResponse({"error": e.detail}, status_code=e.status_code)


@app.exception_handler(RequestValidationError)
async def _val(_, e):
    return JSONResponse({"error": "Некорректный запрос: проверьте, что все даты заполнены."}, status_code=422)


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
    login: str
    password: str


class DecisionIn(BaseModel):
    approve: bool
    comment: str | None = None


class HireIn(BaseModel):
    hire_date: date


api = APIRouter(prefix="/api/v1")


@api.get("/health")
def health():
    return {"status": "ok", "db": db.KIND, "warning": db.warning}


@api.post("/login")
def login(b: LoginIn):
    u = db.q("select * from users where login=%s", (b.login,))
    if not u or not db.check_pw(b.password, u[0]["pass_hash"]):
        raise HTTPException(401, "Неверный логин или пароль")
    t = secrets.token_hex(16)
    db.q("insert into sessions(token_hash,user_id,expires_at) values(%s,%s,%s)",
         (_h(t), u[0]["id"], (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()))
    return {"token": t}


@api.post("/logout")
def logout(authorization: str = Header(default="")):
    db.q("delete from sessions where token_hash=%s", (_h(authorization[7:]),))
    return {"ok": True}


@api.get("/me")
def get_me(u=Depends(me)):
    return {**{k: v for k, v in u.items() if k != "pass_hash"}, "today": today()}


def user_parts(uid, c=None):
    rows = db.q("""select p.start_date s, p.end_date e from vacation_parts p join vacations v on v.id=p.vacation_id
                   where v.user_id=%s and v.status<>'rejected'""", (uid,), c)
    return [(r["s"], r["e"]) for r in rows]


@api.get("/balance")
def balance(on_date: date | None = Query(None, alias="date"), u=Depends(me)):
    on = on_date or today()
    used = sum(plen(p) for p in user_parts(u["id"]) if p[0] <= on)
    a = rules.accrued(u["hire_date"], on)
    return {"date": on, "accrued": a, "reserved": used, "available": a - used}


def create_vacation(c, u, parts, replaces=None):
    if not approvers(u):
        raise HTTPException(422, "Некому согласовать заявку: у вас не назначен руководитель и нет других сотрудников HR.")
    existing = user_parts(u["id"], c)
    err = (rules.validate_parts(parts, today()) or rules.check_balance(u["hire_date"], existing, parts)
           or rules.check_year_limit(existing, parts))
    if err:
        raise HTTPException(422, err)
    v = db.q("insert into vacations(user_id,status,replaces_id) values(%s,'pending',%s) returning *", (u["id"], replaces), c)[0]
    for s, e in parts:
        db.q("insert into vacation_parts(vacation_id,start_date,end_date) values(%s,%s,%s)", (v["id"], s, e), c)
    return v


def cancel_vacation(c, v):
    """До начала дни возвращаются целиком; после начала остаётся использованное (по сегодня включительно).
    Статус меняется атомарным update: два одновременных запроса не отменят и не перенесут заявку дважды."""
    t = today()
    if v["status"] in ("cancelled", "rejected"):
        raise HTTPException(409, "Заявка уже неактивна")
    ps = db.q("select * from vacation_parts where vacation_id=%s", (v["id"],), c)
    if all(p["end_date"] < t for p in ps):
        raise HTTPException(409, "Отпуск уже закончился")
    if not db.q("update vacations set status='cancelled' where id=%s and status in ('pending','approved') returning id", (v["id"],), c):
        raise HTTPException(409, "Заявка уже неактивна")
    db.q("delete from vacation_parts where vacation_id=%s and start_date>%s", (v["id"], t), c)
    db.q("update vacation_parts set end_date=%s where vacation_id=%s and end_date>%s", (t, v["id"], t), c)


def _parts(b: VacIn):
    return [(p.start, p.end) for p in b.parts]


@api.post("/vacations")
def create(b: VacIn, u=Depends(me)):
    with db.connection() as c:
        lock_user(c, u)
        v = create_vacation(c, u, _parts(b))
    for rid in approvers(u):
        note("new_request", v["id"], rid, f"Новая заявка от {u['name']}")
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
        cancel_vacation(c, v)
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
        note("new_request", v["id"], rid, f"Перенос отпуска: {u['name']}")
    ping()
    return v


@api.post("/vacations/{vid}/decision")
def decision(vid: int, b: DecisionIn, u=Depends(me)):
    r = db.q("select v.*, u.manager_id from vacations v join users u on u.id=v.user_id where v.id=%s", (vid,))
    if not r or u["id"] not in approvers({"id": r[0]["user_id"], "manager_id": r[0]["manager_id"]}):
        raise HTTPException(403, "Это не ваш сотрудник")
    v = r[0]
    if not b.approve and not (b.comment or "").strip():
        raise HTTPException(422, "При отклонении нужен комментарий")
    done = db.q("update vacations set status=%s, comment=%s where id=%s and status='pending' returning id",
                ("approved" if b.approve else "rejected", b.comment, vid))
    if not done:
        raise HTTPException(409, "Заявка уже рассмотрена")
    note("decision", vid, v["user_id"], "Отпуск согласован" if b.approve else f"Отпуск отклонён: {b.comment}")
    ping()
    return {"ok": True}


@api.get("/vacations")
def vacations(u=Depends(me)):
    """Свои заявки и заявки, которые согласует пользователь: сотрудников команды; для HR ещё и тех, у кого нет руководителя."""
    scope = "(v.user_id=%s or u.manager_id=%s or (%s and u.manager_id is null and u.id<>%s))"
    args = (u["id"], u["id"], u["role"] == "hr", u["id"])
    rows = db.q(f"""select v.id, v.status, v.comment, v.user_id, u.name, u.team
        from vacations v join users u on u.id=v.user_id where {scope} order by v.id desc""", args)
    parts: dict[int, list] = {}
    for p in db.q(f"""select p.vacation_id vid, p.start_date start, p.end_date "end" from vacation_parts p
                     join vacations v on v.id=p.vacation_id join users u on u.id=v.user_id
                     where {scope} order by p.start_date""", args):
        parts.setdefault(p["vid"], []).append({"start": p["start"], "end": p["end"]})
    for r in rows:
        r["parts"] = parts.get(r["id"], [])
        if r["user_id"] != u["id"] and r["status"] == "pending":
            r["conflicts"] = db.q("""select distinct u2.name, p2.start_date start, p2.end_date "end" from vacations v2
                join users u2 on u2.id=v2.user_id join vacation_parts p2 on p2.vacation_id=v2.id
                where u2.team=%s and u2.id<>%s and v2.status='approved' and exists(
                  select 1 from vacation_parts p where p.vacation_id=%s and p.start_date<=p2.end_date and p.end_date>=p2.start_date)""",
                                  (r["team"], r["user_id"], r["id"]))
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
    db.q("update notifications set read_at=%s where recipient_id=%s and read_at is null",
         (datetime.now(timezone.utc).isoformat(), u["id"]))
    return {"ok": True}


@api.get("/hr/balances")
def hr_balances(u=Depends(me)):
    if u["role"] != "hr":
        raise HTTPException(403, "Только HR")
    out = []
    for x in db.q("select id,name,team,hire_date from users order by name"):
        parts = user_parts(x["id"])
        used = sum(plen(p) for p in parts if p[0] <= today())
        a = rules.accrued(x["hire_date"], today())
        bad = rules.review_balance(x["hire_date"], parts)
        out.append({**x, "accrued": a, "available": a - used, "needsAttention": bool(bad),
                    "problem": (f"К {bad[0][0][0].isoformat()} накоплено {bad[0][1]} дн., а заявки требуют {bad[0][2]} дн." if bad else None)})
    return out


def review_after_hire_change(uid: int, name: str, manager_id: int | None, hire: date):
    """Пересмотр после смены даты выхода: заявки, которые больше не покрываются накоплением, не отменяются сами,
    но сотрудник, руководитель и HR получают по одному уведомлению на заявку (ключ unique в БД)."""
    rows = db.q("""select v.id vid, p.start_date s, p.end_date e from vacations v join vacation_parts p on p.vacation_id=v.id
                   where v.user_id=%s and v.status in ('pending','approved')""", (uid,))
    owner = {}
    for r in rows:
        owner.setdefault((r["s"], r["e"]), r["vid"])
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
            yield ": ok\n\n"
            while True:
                try:
                    await asyncio.wait_for(qq.get(), 15)
                    yield "data: cal\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            subs.discard(qq)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


app.include_router(api)
