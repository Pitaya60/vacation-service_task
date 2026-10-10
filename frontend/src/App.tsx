import { useCallback, useEffect, useRef, useState } from 'react';
import { API, AuthError, call, getToken, hasToken, setToken } from './api';
import { addDays } from './dates';
import type { Data, Health, Me, Part, Role, Vac, HrUser } from './types';
import Calendar from './Calendar';
import { Approvals, BalanceCards, HrOverview, MyRequests, RequestForm } from './views';
import { Icon, Logo, short } from './ui';

const ROLE: Record<Role, string> = { employee: 'Сотрудник', manager: 'Руководитель', hr: 'HR' };
const DEMO = [
  { login: 'ivan', title: 'Иван', role: 'Сотрудник' }, { login: 'olga', title: 'Ольга', role: 'Сотрудник' },
  { login: 'boss', title: 'Игорь', role: 'Руководитель' }, { login: 'hr', title: 'Анна', role: 'HR' },
];
interface Toast { kind: 'ok' | 'err'; text: string }

function Login({ onDone, notice }: { onDone: (me: Me) => void; notice: string }) {
  const [login, setLogin] = useState(''), [password, setPassword] = useState('demo'), [err, setErr] = useState(notice), [busy, setBusy] = useState(false);
  const go = async (l: string, p: string) => {
    setBusy(true); setErr('');
    try { setToken((await call<{ token: string }>('/login', 'POST', { login: l, password: p })).token); onDone(await call<Me>('/me')); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <main className="login">
      <section className="login-brand">
        <div className="brand"><Logo /><span>Отпуска</span></div>
        <h1>Отпуска команды в одном месте</h1>
        <p>Смотрите, сколько дней вам положено, отправляйте заявку и следите за решением. Руководитель согласует, HR видит всю компанию.</p>
      </section>
      <section className="login-form">
        <h2>Вход</h2>
        <div className="field"><label htmlFor="lg">Логин</label><input id="lg" autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go(login, password)} /></div>
        <div className="field"><label htmlFor="pw">Пароль</label><input id="pw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go(login, password)} /></div>
        {err && <div className="alert" role="alert">{err}</div>}
        <button className="btn primary wide" disabled={busy || !login} onClick={() => go(login, password)}>Войти</button>
        <div className="demo">
          <p className="muted">Демо-аккаунты, пароль demo. Нажмите, чтобы войти сразу:</p>
          <div className="demo-list">{DEMO.map((d) => (
            <button key={d.login} className="demo-btn" disabled={busy} onClick={() => go(d.login, 'demo')}><b>{d.title}</b><span>{d.role}</span></button>))}</div>
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null), [booting, setBooting] = useState(hasToken());
  const [health, setHealth] = useState<Health | null>(null), [data, setData] = useState<Data | null>(null);
  const [tab, setTab] = useState(''), [tick, setTick] = useState(0), [fDate, setFDate] = useState('');
  const [resched, setResched] = useState<Vac | null>(null), [toast, setToast] = useState<Toast | null>(null), [notesOpen, setNotesOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const timer = useRef<number>();

  const say = useCallback((kind: Toast['kind'], text: string) => {
    setToast({ kind, text }); window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setToast(null), kind === 'ok' ? 4000 : 8000);
  }, []);
  const logout = useCallback((msg = '') => { setToken(''); setMe(null); setData(null); setTab(''); setNotice(msg); setResched(null); }, []);
  const refresh = () => setTick((t) => t + 1);

  const start = useCallback((m: Me) => { setMe(m); setFDate(addDays(m.today, 60)); setTab(m.role === 'hr' ? 'hr' : m.role === 'manager' ? 'appr' : 'me'); setNotice(''); call<Health>('/health').then(setHealth).catch(() => undefined); }, []);

  useEffect(() => { if (hasToken()) call<Me>('/me').then(start).catch(() => setToken('')).finally(() => setBooting(false)); }, [start]);

  useEffect(() => {
    if (!me) return;
    const es = new EventSource(`${API}/events?token=${getToken()}`);
    es.onmessage = refresh;
    return () => es.close();
  }, [me]);

  useEffect(() => {
    if (!me || !fDate) return;
    let live = true;
    (async () => {
      const [bal, fc, vac, cal, notes, hr] = await Promise.all([
        call('/balance'), call(`/balance?date=${fDate}`), call('/vacations'),
        call('/calendar?scope=' + (me.role === 'hr' ? 'company' : 'team')), call('/notifications'),
        me.role === 'hr' ? call('/hr/balances') : Promise.resolve([]),
      ]);
      if (live) setData({ bal, fc, vac, cal, notes, hr });
    })().catch((e) => { if (e instanceof AuthError) logout('Сессия закончилась, войдите снова.'); else say('err', e.message); });
    return () => { live = false; };
  }, [me, tick, fDate, logout, say]);

  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && setNotesOpen(false); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, []);

  if (booting) return <div className="boot">Загрузка…</div>;
  if (!me) return <Login onDone={start} notice={notice} />;

  const waiting = (data?.vac ?? []).filter((v) => v.user_id !== me.id && v.status === 'pending').length;
  const tabs = {
    employee: [['me', 'Мой отпуск'], ['team', 'Календарь команды']],
    manager: [['appr', 'Согласование'], ['team', 'Календарь команды'], ['me', 'Мой отпуск']],
    hr: [['hr', 'Сотрудники и остатки'], ['company', 'Календарь компании'], ['me', 'Мой отпуск']],
  }[me.role];

  const send = async (parts: Part[]) => {
    if (resched) { await call(`/vacations/${resched.id}/reschedule`, 'POST', { parts }); setResched(null); say('ok', 'Перенос отправлен руководителю на согласование.'); }
    else { await call('/vacations', 'POST', { parts }); say('ok', 'Заявка отправлена руководителю.'); }
    refresh();
  };
  const cancel = async (v: Vac) => {
    if (!window.confirm('Отменить заявку? Неиспользованные дни вернутся в остаток.')) return;
    try { await call(`/vacations/${v.id}/cancel`, 'POST'); say('ok', 'Заявка отменена, дни вернулись в остаток.'); refresh(); } catch (e) { say('err', (e as Error).message); }
  };
  const decide = async (v: Vac, approve: boolean, comment?: string) => {
    await call(`/vacations/${v.id}/decision`, 'POST', { approve, comment });
    say('ok', approve ? `Отпуск сотрудника ${v.name} согласован.` : `Заявка сотрудника ${v.name} отклонена.`); refresh();
  };
  const saveHire = async (u: HrUser, hd: string) => {
    try { await call(`/users/${u.id}/hire-date`, 'PATCH', { hire_date: hd }); say('ok', `Дата выхода сотрудника ${u.name} обновлена, накопление пересчитано.`); refresh(); } catch (e) { say('err', (e as Error).message); }
  };

  return (
    <div className={`app role-${me.role}`}>
      <header className="top">
        <div className="top-in">
          <div className="brand"><Logo /><span>Отпуска</span></div>
          <div className="who">
            <div className="notes">
              <button className="btn icon bare" aria-label="Уведомления" aria-expanded={notesOpen} onClick={() => setNotesOpen(!notesOpen)}><Icon name="bell" /></button>
              {notesOpen && (
                <div className="pop" role="dialog" aria-label="Уведомления">
                  <h3>Уведомления</h3>
                  {data?.notes.length ? <ul>{data.notes.map((n) => <li key={n.id}>{n.text}</li>)}</ul> : <p className="muted">Пока ничего нового.</p>}
                </div>)}
            </div>
            <div className="me"><b>{short(me.name)}</b><span>{ROLE[me.role] === me.team ? me.team : `${ROLE[me.role]}, ${me.team}`}</span></div>
            <button className="btn bare" onClick={() => logout()}>Выйти</button>
          </div>
        </div>
        <nav className="tabs" aria-label="Разделы">
          {tabs.map(([id, label]) => (
            <button key={id} className={`tab${tab === id ? ' on' : ''}`} aria-current={tab === id ? 'page' : undefined} onClick={() => setTab(id)}>
              {label}{id === 'appr' && waiting > 0 && <span className="count">{waiting}</span>}</button>))}
        </nav>
      </header>

      <main className="page">
        {health?.db === 'sqlite' && <div className="warn" role="note"><b>Работает запасная база SQLite.</b> Встроенный PostgreSQL не запустился. {health.warning}</div>}
        {toast && <div className={`toast ${toast.kind}`} role={toast.kind === 'err' ? 'alert' : 'status'}>{toast.text}<button className="btn icon bare" aria-label="Закрыть" onClick={() => setToast(null)}><Icon name="x" /></button></div>}
        {!data ? <p className="muted">Загружаю данные…</p> : (<>
          {tab === 'me' && (<>
            <BalanceCards me={me} bal={data.bal} fc={data.fc} date={fDate} setDate={setFDate} />
            <RequestForm today={me.today} resched={resched} onSubmit={send} onStopResched={() => setResched(null)} />
            <MyRequests me={me} vac={data.vac} onCancel={cancel} onResched={(v) => { setResched(v); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />
          </>)}
          {tab === 'appr' && <Approvals me={me} vac={data.vac} onDecide={decide} />}
          {tab === 'team' && <Calendar rows={data.cal} today={me.today} />}
          {tab === 'company' && <Calendar rows={data.cal} today={me.today} byTeam />}
          {tab === 'hr' && <HrOverview users={data.hr} cal={data.cal} today={me.today} onSaveHire={saveHire} />}
        </>)}
      </main>
    </div>
  );
}
