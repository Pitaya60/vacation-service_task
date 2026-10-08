import Fastify from 'fastify';
import cors from '@fastify/cors';
import pg from 'pg';
import crypto from 'crypto';
import { accrued, validateParts, checkBalance, day, iso, len, Part } from './rules.js';

pg.types.setTypeParser(1082, (v) => v); // date -> строка
const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
const REMIND = +(process.env.REMIND_DAYS ?? 3);
const today = () => new Date().toISOString().slice(0, 10);
const q = async (s: string, p: any[] = [], c: any = pool) => (await c.query(s, p)).rows;
const ping = () => pool.query("select pg_notify('cal','x')");
const sha = (s: string) => crypto.createHash('sha256').update(s).digest('hex');

// «Ровно одно»: уникальный ключ (type, vacation_id, recipient_id) + on conflict do nothing.
async function note(type: string, vid: number, rid: number | null, text: string) {
  if (!rid) return;
  const r = await q('insert into notifications(type,vacation_id,recipient_id,text) values($1,$2,$3,$4) on conflict do nothing returning id', [type, vid, rid, text]);
  if (r.length) console.log(`[notify] ${type} -> user ${rid}: ${text}`);
}

const app = Fastify();
await app.register(cors, { origin: true });
const tokens = new Map<string, any>();
const fail = (msg: string, code = 400) => Object.assign(new Error(msg), { code });
app.setErrorHandler((e: any, _r, rep) => rep.code(e.code && e.code < 600 ? e.code : 500).send({ error: e.message }));
app.addHook('preHandler', async (req) => {
  if (req.url === '/login' || req.url.startsWith('/events') || req.method === 'OPTIONS') return;
  const u = tokens.get((req.headers.authorization ?? '').slice(7));
  if (!u) throw fail('Требуется вход', 401);
  (req as any).me = (await q('select * from users where id=$1', [u.id]))[0];
});

app.post('/login', async (req: any) => {
  const [u] = await q('select * from users where login=$1 and pass_hash=$2', [req.body.login, sha(req.body.password)]);
  if (!u) throw fail('Неверный логин или пароль', 401);
  const token = crypto.randomUUID();
  tokens.set(token, { id: u.id });
  return { token };
});

app.get('/me', async (req: any) => ({ ...req.me, pass_hash: undefined, today: today() }));

const userParts = (uid: number, c: any = pool) =>
  q(`select p.start_date start, p.end_date "end" from vacation_parts p join vacations v on v.id=p.vacation_id
     where v.user_id=$1 and v.status<>'rejected'`, [uid], c);

app.get('/balance', async (req: any) => {
  const on = req.query.date || today();
  const parts: Part[] = (await userParts(req.me.id)).filter((p: Part) => day(p.start) <= day(on));
  const a = accrued(req.me.hire_date, on), used = parts.reduce((s, p) => s + len(p), 0);
  return { date: on, accrued: a, reserved: used, available: a - used };
});

async function createVacation(c: any, me: any, parts: Part[], replaces: number | null = null) {
  const err = validateParts(parts) ?? checkBalance(me.hire_date, await userParts(me.id, c), parts);
  if (err) throw fail(err, 422);
  const [v] = await q('insert into vacations(user_id,status,replaces_id) values($1,$2,$3) returning *', [me.id, 'pending', replaces], c);
  for (const p of parts) await q('insert into vacation_parts(vacation_id,start_date,end_date) values($1,$2,$3)', [v.id, p.start, p.end], c);
  return v;
}

// Отмена: до начала дни возвращаются целиком; после начала остаётся только использованное (по сегодня включительно).
async function cancelVacation(c: any, v: any) {
  const t = today();
  if (['cancelled', 'rejected'].includes(v.status)) throw fail('Заявка уже неактивна', 409);
  const ps = await q('select * from vacation_parts where vacation_id=$1', [v.id], c);
  if (ps.every((p: any) => day(p.end_date) < day(t))) throw fail('Отпуск уже закончился', 409);
  await q('delete from vacation_parts where vacation_id=$1 and start_date>$2', [v.id, t], c);
  await q('update vacation_parts set end_date=$2 where vacation_id=$1 and end_date>$2', [v.id, t], c);
  await q("update vacations set status='cancelled' where id=$1", [v.id], c);
}

async function tx<T>(fn: (c: any) => Promise<T>) {
  const c = await pool.connect();
  try { await c.query('begin'); const r = await fn(c); await c.query('commit'); return r; }
  catch (e) { await c.query('rollback'); throw e; } finally { c.release(); }
}

app.post('/vacations', async (req: any) => {
  const v = await tx((c) => createVacation(c, req.me, req.body.parts));
  await note('new_request', v.id, req.me.manager_id, `Новая заявка от ${req.me.name}`);
  await ping(); return v;
});

app.post('/vacations/:id/cancel', async (req: any) => {
  const [v] = await q('select * from vacations where id=$1 and user_id=$2', [req.params.id, req.me.id]);
  if (!v) throw fail('Не найдено', 404);
  await tx((c) => cancelVacation(c, v)); await ping(); return { ok: true };
});

// Перенос = атомарно: отмена старой + новая заявка на согласование.
app.post('/vacations/:id/reschedule', async (req: any) => {
  const [old] = await q('select * from vacations where id=$1 and user_id=$2', [req.params.id, req.me.id]);
  if (!old) throw fail('Не найдено', 404);
  const v = await tx(async (c) => { await cancelVacation(c, old); return createVacation(c, req.me, req.body.parts, old.id); });
  await note('new_request', v.id, req.me.manager_id, `Перенос отпуска: ${req.me.name}`);
  await ping(); return v;
});

app.post('/vacations/:id/decision', async (req: any) => {
  const { approve, comment } = req.body;
  const [v] = await q(`select v.*, u.manager_id from vacations v join users u on u.id=v.user_id where v.id=$1`, [req.params.id]);
  if (!v || v.manager_id !== req.me.id) throw fail('Это не ваш сотрудник', 403);
  if (v.status !== 'pending') throw fail('Заявка уже рассмотрена', 409);
  if (!approve && !comment?.trim()) throw fail('При отклонении нужен комментарий', 422);
  await q('update vacations set status=$2, comment=$3 where id=$1', [v.id, approve ? 'approved' : 'rejected', comment ?? null]);
  await note('decision', v.id, v.user_id, approve ? 'Отпуск согласован' : `Отпуск отклонён: ${comment}`);
  await ping(); return { ok: true };
});

app.get('/vacations', async (req: any) => {
  const rows = await q(`select v.id, v.status, v.comment, v.user_id, u.name, u.team,
      (select json_agg(json_build_object('start',p.start_date,'end',p.end_date) order by p.start_date) from vacation_parts p where p.vacation_id=v.id) parts
      from vacations v join users u on u.id=v.user_id
      where v.user_id=$1 or u.manager_id=$1 order by v.id desc`, [req.me.id]);
  for (const r of rows) if (r.user_id !== req.me.id && r.status === 'pending')
    r.conflicts = await q(`select distinct u2.name, p2.start_date start, p2.end_date "end" from vacations v2
      join users u2 on u2.id=v2.user_id join vacation_parts p2 on p2.vacation_id=v2.id
      where u2.team=$1 and u2.id<>$2 and v2.status='approved'
      and exists(select 1 from vacation_parts p where p.vacation_id=$3 and p.start_date<=p2.end_date and p.end_date>=p2.start_date)`,
      [r.team, r.user_id, r.id]);
  return rows;
});

app.get('/calendar', async (req: any) => {
  const company = req.query.scope === 'company';
  if (company && req.me.role !== 'hr') throw fail('Только HR', 403);
  return q(`select v.id, v.status, u.name, u.team, p.start_date start, p.end_date "end" from vacations v
    join users u on u.id=v.user_id join vacation_parts p on p.vacation_id=v.id
    where v.status in('pending','approved') and ($1 or u.team=$2) order by p.start_date`, [company, req.me.team]);
});

app.get('/notifications', async (req: any) => q('select * from notifications where recipient_id=$1 order by id desc limit 30', [req.me.id]));

app.get('/hr/balances', async (req: any) => {
  if (req.me.role !== 'hr') throw fail('Только HR', 403);
  const users = await q('select id,name,team,hire_date from users order by name');
  return Promise.all(users.map(async (u: any) => {
    const parts: Part[] = await userParts(u.id), t = today();
    const used = parts.filter((p) => day(p.start) <= day(t)).reduce((s, p) => s + len(p), 0);
    const a = accrued(u.hire_date, t);
    return { ...u, accrued: a, available: a - used, needsAttention: !!checkBalance(u.hire_date, [], parts) };
  }));
});

// Смена даты выхода: остаток считается функцией, поэтому пересчёт автоматический; конфликты видны в needsAttention.
app.patch('/users/:id/hire-date', async (req: any) => {
  if (req.me.role !== 'hr') throw fail('Только HR', 403);
  await q('update users set hire_date=$2 where id=$1', [req.params.id, req.body.hire_date]);
  await ping(); return { ok: true };
});

// SSE поверх Postgres LISTEN/NOTIFY — работает и при нескольких инстансах backend.
const clients = new Set<any>();
app.get('/events', (req: any, reply) => {
  if (!tokens.has(req.query.token)) return reply.code(401).send();
  reply.hijack();
  reply.raw.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Access-Control-Allow-Origin': '*' });
  clients.add(reply.raw); req.raw.on('close', () => clients.delete(reply.raw));
});
const lc = await pool.connect();
await lc.query('listen cal');
lc.on('notification', () => clients.forEach((c) => c.write('data: cal\n\n')));

// Напоминание за REMIND дней до начала; идемпотентно за счёт уникального ключа уведомлений.
async function remind() {
  const rows = await q(`select v.id, v.user_id, u.manager_id from vacations v join users u on u.id=v.user_id
    where v.status='approved' and (select min(start_date) from vacation_parts where vacation_id=v.id)=$1`, [iso(day(today()) + REMIND)]);
  for (const r of rows) for (const rid of [r.user_id, r.manager_id])
    await note('reminder', r.id, rid, `Отпуск начнётся через ${REMIND} дн.`);
}
setInterval(() => remind().catch(console.error), 60_000);

await app.listen({ port: 3001, host: '0.0.0.0' });
