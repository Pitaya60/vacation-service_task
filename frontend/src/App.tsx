import { useEffect, useState } from 'react';
const API = (import.meta as any).env.VITE_API ?? 'http://localhost:8000/api/v1';
let tok = '';
const call = async (p: string, m = 'GET', b?: any) => {
  const r = await fetch(API + p, { method: m, headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok }, body: b ? JSON.stringify(b) : undefined });
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j;
};
const fmt = (p: any) => `${p.start} — ${p.end}`;

export default function App() {
  const [me, setMe] = useState<any>(null), [err, setErr] = useState(''), [tick, setTick] = useState(0);
  const [d, setD] = useState<any>({}), [on, setOn] = useState(''), [parts, setParts] = useState([{ start: '', end: '' }]);
  const [login, setLogin] = useState({ login: 'ivan', password: 'demo' });
  const guard = (f: () => Promise<any>) => f().then(() => setErr('')).catch((e) => setErr(e.message));

  const signIn = () => guard(async () => {
    tok = (await call('/login', 'POST', login)).token;
    setMe(await call('/me'));
    new EventSource(`${API}/events?token=${tok}`).onmessage = () => setTick((t) => t + 1);
  });
  useEffect(() => { if (me) guard(async () => setD({
    bal: await call('/balance' + (on ? `?date=${on}` : '')), vac: await call('/vacations'),
    cal: await call('/calendar?scope=' + (me.role === 'hr' ? 'company' : 'team')), notes: await call('/notifications'),
    hr: me.role === 'hr' ? await call('/hr/balances') : [] })); }, [me, tick, on]);

  if (!me) return (<div style={{ padding: 20 }}><h2>Вход</h2>
    <input value={login.login} onChange={(e) => setLogin({ ...login, login: e.target.value })} />{' '}
    <input type="password" value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} />{' '}
    <button onClick={signIn}>Войти</button> <p>Демо: hr / boss / ivan / olga, пароль demo</p><b style={{ color: 'red' }}>{err}</b></div>);

  return (<div style={{ padding: 20, fontFamily: 'sans-serif', maxWidth: 900 }}>
    <h2>{me.name} ({me.role}, {me.team})</h2><b style={{ color: 'red' }}>{err}</b>
    <h3>Остаток</h3>
    На дату <input type="date" value={on || me.today} onChange={(e) => setOn(e.target.value)} />:
    накоплено {d.bal?.accrued}, зарезервировано {d.bal?.reserved}, <b>доступно {d.bal?.available}</b>
    <h3>Новая заявка</h3>
    {parts.map((p, i) => (<div key={i}>
      <input type="date" value={p.start} onChange={(e) => setParts(parts.map((x, j) => j === i ? { ...x, start: e.target.value } : x))} />
      {' — '}<input type="date" value={p.end} onChange={(e) => setParts(parts.map((x, j) => j === i ? { ...x, end: e.target.value } : x))} /></div>))}
    <button onClick={() => setParts([...parts, { start: '', end: '' }])}>+ часть</button>{' '}
    <button onClick={() => guard(() => call('/vacations', 'POST', { parts }))}>Подать</button>
    <h3>Заявки</h3>
    {d.vac?.map((v: any) => (<div key={v.id} style={{ borderBottom: '1px solid #ddd', padding: 4 }}>
      #{v.id} {v.name} — <b>{v.status}</b> {v.comment && `(${v.comment})`}: {v.parts?.map(fmt).join('; ')}{' '}
      {v.user_id === me.id && ['pending', 'approved'].includes(v.status) &&
        <button onClick={() => guard(() => call(`/vacations/${v.id}/cancel`, 'POST'))}>Отменить</button>}
      {v.user_id === me.id && v.status === 'approved' &&
        <button onClick={() => guard(() => call(`/vacations/${v.id}/reschedule`, 'POST', { parts }))}>Перенести на даты из формы</button>}
      {v.conflicts?.length > 0 && <div style={{ color: 'darkorange' }}>⚠ Пересечения в команде: {v.conflicts.map((c: any) => `${c.name} ${fmt(c)}`).join('; ')}</div>}
      {v.user_id !== me.id && v.status === 'pending' && <>
        <button onClick={() => guard(() => call(`/vacations/${v.id}/decision`, 'POST', { approve: true }))}>Согласовать</button>
        <button onClick={() => { const c = prompt('Причина отказа'); guard(() => call(`/vacations/${v.id}/decision`, 'POST', { approve: false, comment: c })); }}>Отклонить</button></>}
    </div>))}
    <h3>Календарь {me.role === 'hr' ? 'компании' : 'команды'} (обновляется само)</h3>
    {d.cal?.map((c: any, i: number) => <div key={i}>{c.name}: {fmt(c)} [{c.status}]</div>)}
    {me.role === 'hr' && <><h3>Остатки (HR)</h3>
      {d.hr?.map((u: any) => <div key={u.id}>{u.name} ({u.team}), выход {u.hire_date}: накоплено {u.accrued}, доступно {u.available}{u.needsAttention && ' ⚠ требует внимания'}</div>)}</>}
    <h3>Уведомления</h3>{d.notes?.map((n: any) => <div key={n.id}>{n.text}</div>)}
  </div>);
}
