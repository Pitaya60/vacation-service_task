import { useEffect, useState } from 'react';
import type { Balance, CalRow, HrUser, Me, Part, Vac } from './types';
import { addDays, days, daysLabel, full, range } from './dates';
import { Empty, Icon, StatusChip, short } from './ui';

/* ---------- Мой отпуск ---------- */

export function BalanceCards({ me, bal, fc, date, setDate }: { me: Me; bal: Balance | undefined; fc: Balance | undefined; date: string; setDate: (d: string) => void }) {
  return (
    <div className="balance">
      <section className="hero" aria-label="Остаток на сегодня">
        <p className="hero-label">Доступно сегодня</p>
        <p className="hero-num"><span>{bal?.available ?? '–'}</span><small>{bal ? daysLabel(bal.available).replace(/^\d+ /, '') : ''}</small></p>
        <p className="hero-sub">Накоплено {bal?.accrued ?? '–'}, использовано {bal?.reserved ?? '–'}. Вы работаете с {full(me.hire_date)}</p>
      </section>
      <section className="panel forecast" aria-label="Прогноз на дату">
        <label htmlFor="fdate">Сколько накопится к дате</label>
        <input id="fdate" type="date" value={date} min={me.today} onChange={(e) => e.target.value && setDate(e.target.value)} />
        <p className="forecast-num"><b>{fc?.accrued ?? '–'}</b> {fc ? daysLabel(fc.accrued).replace(/^\d+ /, '') : ''} накоплено</p>
        <p className="muted">Из них можно взять {fc?.available ?? '–'}: остальное уже занято вашими заявками до этой даты.</p>
      </section>
    </div>
  );
}

export function RequestForm({ today, resched, onSubmit, onStopResched }: {
  today: string; resched: Vac | null; onSubmit: (parts: Part[]) => Promise<void>; onStopResched: () => void;
}) {
  const blank = (): Part => ({ start: '', end: '' });
  const [parts, setParts] = useState<Part[]>([blank()]);
  const [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { setErr(''); }, [resched?.id]);
  const set = (i: number, k: keyof Part, v: string) => setParts(parts.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  const len = (p: Part) => (p.start && p.end && p.end >= p.start ? days(p.start, p.end) : 0);
  const total = parts.reduce((s, p) => s + len(p), 0);
  const ready = parts.every((p) => p.start && p.end);

  const submit = async () => {
    setBusy(true); setErr('');
    try { await onSubmit(parts); setParts([blank()]); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <section className="panel" aria-label="Заявка на отпуск">
      <div className="panel-head">
        <h2>{resched ? `Перенос заявки №${resched.id}` : 'Новая заявка'}</h2>
        {resched && <button className="btn ghost" onClick={onStopResched}>Не переносить</button>}
      </div>
      <p className="muted">{resched
        ? `Сейчас отпуск: ${resched.parts.map((p) => range(p.start, p.end)).join(', ')}. Старая заявка отменится, новая уйдёт на согласование.`
        : 'Можно разбить отпуск на части: не больше трёх, одна от 14 дней, остальные от 5.'}</p>
      {parts.map((p, i) => (
        <div className="part" key={i}>
          <div className="field"><label htmlFor={`s${i}`}>{parts.length > 1 ? `Часть ${i + 1}: с` : 'С'}</label>
            <input id={`s${i}`} type="date" min={addDays(today, 1)} value={p.start} onChange={(e) => set(i, 'start', e.target.value)} /></div>
          <div className="field"><label htmlFor={`e${i}`}>По</label>
            <input id={`e${i}`} type="date" min={p.start || addDays(today, 1)} value={p.end} onChange={(e) => set(i, 'end', e.target.value)} /></div>
          <span className={`len${len(p) ? ' on' : ''}`}>{len(p) ? daysLabel(len(p)) : ''}</span>
          {parts.length > 1 && <button className="btn icon" aria-label={`Убрать часть ${i + 1}`} onClick={() => setParts(parts.filter((_, j) => j !== i))}><Icon name="x" /></button>}
        </div>
      ))}
      {err && <div className="alert" role="alert">{err}</div>}
      <div className="actions">
        <button className="btn ghost" disabled={parts.length >= 3} onClick={() => setParts([...parts, blank()])}><Icon name="plus" />Добавить часть</button>
        <span className="total">{total ? `Всего ${daysLabel(total)}` : ''}</span>
        <button className="btn primary" disabled={!ready || busy} onClick={submit}>{resched ? 'Отправить перенос' : 'Отправить на согласование'}</button>
      </div>
    </section>
  );
}

export function MyRequests({ me, vac, onCancel, onResched }: { me: Me; vac: Vac[]; onCancel: (v: Vac) => void; onResched: (v: Vac) => void }) {
  const mine = vac.filter((v) => v.user_id === me.id);
  return (
    <section className="panel" aria-label="Мои заявки">
      <h2>Мои заявки</h2>
      {mine.length === 0 ? <Empty title="Заявок пока нет">Выберите даты в форме выше и отправьте заявку руководителю.</Empty> : (
        <ul className="list">{mine.map((v) => (
          <li key={v.id} className="item">
            <div className="item-main">
              <b>{v.parts.map((p) => range(p.start, p.end)).join(', ') || 'Без дат'}</b>
              <span className="muted">{daysLabel(v.parts.reduce((s, p) => s + days(p.start, p.end), 0))}, заявка №{v.id}</span>
              {v.comment && <span className={v.status === 'rejected' ? 'why' : 'muted'}>Комментарий руководителя: {v.comment}</span>}
            </div>
            <StatusChip s={v.status} />
            {['pending', 'approved'].includes(v.status) && (
              <div className="item-actions">
                {v.status === 'approved' && <button className="btn ghost" onClick={() => onResched(v)}>Перенести</button>}
                <button className="btn danger" onClick={() => onCancel(v)}>Отменить</button>
              </div>)}
          </li>))}
        </ul>)}
    </section>
  );
}

/* ---------- Согласование (руководитель) ---------- */

function Decision({ v, onDecide }: { v: Vac; onDecide: (v: Vac, approve: boolean, comment?: string) => Promise<void> }) {
  const [rejecting, setRejecting] = useState(false), [reason, setReason] = useState(''), [err, setErr] = useState('');
  const run = (approve: boolean) => onDecide(v, approve, reason).catch((e) => setErr((e as Error).message));
  return (
    <li className="item col">
      <div className="item-top">
        <div className="item-main">
          <b>{short(v.name)}</b>
          <span>{v.parts.map((p) => range(p.start, p.end)).join(', ')}</span>
          <span className="muted">{daysLabel(v.parts.reduce((s, p) => s + days(p.start, p.end), 0))}, заявка №{v.id}</span>
        </div>
        <StatusChip s={v.status} />
      </div>
      {v.conflicts && v.conflicts.length > 0 && (
        <div className="warn" role="note"><b>Пересекается с отпуском в команде:</b>{' '}
          {v.conflicts.map((c) => `${c.name}, ${range(c.start, c.end)}`).join('; ')}</div>)}
      {rejecting ? (
        <div className="reject">
          <label htmlFor={`r${v.id}`}>Причина отказа</label>
          <textarea id={`r${v.id}`} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: в эти даты релиз" />
          {err && <div className="alert" role="alert">{err}</div>}
          <div className="actions">
            <button className="btn ghost" onClick={() => { setRejecting(false); setErr(''); }}>Назад</button>
            <button className="btn danger solid" disabled={!reason.trim()} onClick={() => run(false)}>Отклонить заявку</button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="btn ghost" onClick={() => setRejecting(true)}>Отклонить</button>
          <button className="btn primary" onClick={() => run(true)}>Согласовать</button>
        </div>)}
    </li>
  );
}

export function Approvals({ me, vac, onDecide }: { me: Me; vac: Vac[]; onDecide: (v: Vac, approve: boolean, comment?: string) => Promise<void> }) {
  const others = vac.filter((v) => v.user_id !== me.id);
  const wait = others.filter((v) => v.status === 'pending'), done = others.filter((v) => v.status !== 'pending');
  return (<>
    <section className="panel" aria-label="Ждут решения">
      <h2>Ждут вашего решения{wait.length > 0 && <span className="count">{wait.length}</span>}</h2>
      {wait.length === 0 ? <Empty title="Новых заявок нет">Когда сотрудник отправит заявку, она появится здесь, а на странице обновится само.</Empty>
        : <ul className="list">{wait.map((v) => <Decision key={v.id} v={v} onDecide={onDecide} />)}</ul>}
    </section>
    {done.length > 0 && (
      <section className="panel" aria-label="Принятые решения">
        <h2>Уже рассмотрено</h2>
        <ul className="list">{done.map((v) => (
          <li key={v.id} className="item">
            <div className="item-main"><b>{short(v.name)}</b><span>{v.parts.map((p) => range(p.start, p.end)).join(', ')}</span>
              {v.comment && <span className="muted">Комментарий: {v.comment}</span>}</div>
            <StatusChip s={v.status} />
          </li>))}</ul>
      </section>)}
  </>);
}

/* ---------- HR ---------- */

function HrRow({ u, save }: { u: HrUser; save: (hd: string) => Promise<void> }) {
  const [hd, setHd] = useState(u.hire_date), [busy, setBusy] = useState(false);
  useEffect(() => setHd(u.hire_date), [u.hire_date]);
  const changed = hd !== u.hire_date && !!hd;
  return (
    <tr>
      <td><b>{short(u.name)}</b><span className="muted block">{u.team}</span></td>
      <td><div className="inline"><input aria-label={`Дата выхода: ${u.name}`} type="date" value={hd} onChange={(e) => setHd(e.target.value)} />
        {changed && <button className="btn primary sm" disabled={busy} onClick={() => { setBusy(true); save(hd).finally(() => setBusy(false)); }}>Сохранить</button>}</div></td>
      <td className="num">{u.accrued}</td>
      <td className="num"><b>{u.available}</b></td>
      <td>{u.needsAttention ? <span className="chip chip-pending">Проверить заявки</span> : <span className="muted">В порядке</span>}</td>
    </tr>
  );
}

export function HrOverview({ users, cal, today, onSaveHire }: { users: HrUser[]; cal: CalRow[]; today: string; onSaveHire: (u: HrUser, hd: string) => Promise<void> }) {
  const away = new Set(cal.filter((r) => r.status === 'approved' && r.start <= today && today <= r.end).map((r) => r.name)).size;
  const pending = new Set(cal.filter((r) => r.status === 'pending').map((r) => r.id)).size;
  const attention = users.filter((u) => u.needsAttention).length;
  return (<>
    <div className="stats">
      <div className="stat"><b>{users.length}</b><span>сотрудников в компании</span></div>
      <div className="stat"><b>{away}</b><span>в отпуске сегодня</span></div>
      <div className="stat"><b>{pending}</b><span>{pending === 1 ? 'заявка ждёт' : 'заявок ждут'} согласования</span></div>
      <div className={`stat${attention ? ' alert-stat' : ''}`}><b>{attention}</b><span>требуют проверки после смены даты выхода</span></div>
    </div>
    <section className="panel" aria-label="Остатки по сотрудникам">
      <h2>Остатки по сотрудникам</h2>
      <p className="muted">Измените дату выхода на работу, и накопление пересчитается у всех сразу.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Сотрудник</th><th>Дата выхода</th><th className="num">Накоплено</th><th className="num">Доступно</th><th>Состояние</th></tr></thead>
        <tbody>{users.map((u) => <HrRow key={u.id} u={u} save={(hd) => onSaveHire(u, hd)} />)}</tbody>
      </table></div>
    </section>
  </>);
}
