import { useEffect, useState } from 'react';
import type { Balance, CalRow, HrUser, Me, Part, Vac } from './types';
import { addDays, dayMonth, days, daysLabel, full, plural, range, whenShort } from './dates';
import { Avatar, Empty, Icon, StatusChip, short } from './ui';

const word = (n: number) => plural(n, ['день', 'дня', 'дней']);
const dates = (v: Vac) => v.parts.map((p) => range(p.start, p.end)).join(', ') || 'Без дат';

/* ---------- Мой отпуск ---------- */

/** Полоса из плиток: одна плитка = один день. Видно, сколько дней уже отгулено, сколько занято заявками и сколько свободно. */
function DayStrip({ bal }: { bal: Balance }) {
  const MAX = 160;
  const total = Math.max(bal.accrued, bal.used + bal.planned);
  const kinds: string[] = [];
  for (let i = 0; i < Math.min(total, MAX); i++) {
    const k = i < bal.used ? 'used' : i < bal.used + bal.planned ? 'planned' : 'free';
    kinds.push(i >= bal.accrued ? `${k} later` : k);
  }
  return (
    <div className="strip" role="img" aria-label={`Накоплено ${daysLabel(bal.accrued)}: использовано ${bal.used}, в заявках ${bal.planned}, свободно ${Math.max(0, bal.accrued - bal.used - bal.planned)}`}>
      {kinds.map((k, i) => <i key={i} className={`tile ${k}`} />)}
      {total > MAX && <span className="strip-more">+{total - MAX}</span>}
    </div>
  );
}

export function BalanceCards({ me, bal, fc, date, setDate }: { me: Me; bal: Balance; fc: Balance; date: string; setDate: (d: string) => void }) {
  const rest = bal.accrued - bal.used - bal.planned;
  return (
    <div className="balance">
      <section className="hero" aria-label="Остаток отпуска">
        <div className="hero-top">
          <div>
            <p className="hero-label">Можно запланировать</p>
            <p className="hero-num"><span>{bal.free}</span><small>{word(bal.free)}</small></p>
          </div>
          <dl className="facts">
            <div><dt><i className="key used" />Использовано</dt><dd>{bal.used}</dd></div>
            <div><dt><i className="key planned" />В заявках</dt><dd>{bal.planned}</dd></div>
            <div><dt><i className="key free" />Накоплено всего</dt><dd>{bal.accrued}</dd></div>
          </dl>
        </div>
        <DayStrip bal={bal} />
        <p className="hero-sub">
          {rest < 0
            ? `Заявки уже занимают дни, которые накопятся к их началу. `
            : bal.free < rest ? `Часть свободных дней нужна будущим заявкам, поэтому сейчас можно взять меньше. ` : ''}
          За год начисляется {bal.annual} дней пропорционально отработанному времени. Вы работаете с {full(me.hire_date).replace(/\.$/, '')}.
        </p>
      </section>
      <section className="panel forecast" aria-label="Прогноз на дату">
        <label htmlFor="fdate">Сколько будет к дате</label>
        <input id="fdate" type="date" value={date} min={me.today} onChange={(e) => e.target.value && setDate(e.target.value)} />
        <p className="forecast-num"><b>{fc.accrued}</b> {word(fc.accrued)} накопится к {dayMonth(date)}</p>
        <p className="muted">Если начать отпуск в этот день, можно взять до {daysLabel(fc.free)}: часть накопленного уже занята вашими заявками.</p>
      </section>
    </div>
  );
}

function Check({ ok, children }: { ok: boolean | null; children: string }) {
  return <li className={ok === null ? '' : ok ? 'ok' : 'bad'}><Icon name={ok ? 'check' : ok === null ? 'dot' : 'x'} size={16} />{children}</li>;
}

export function RequestForm({ today, resched, approvers, free, onSubmit, onStopResched }: {
  today: string; resched: Vac | null; approvers: string[]; free: number; onSubmit: (parts: Part[]) => Promise<void>; onStopResched: () => void;
}) {
  const blank = (): Part => ({ start: '', end: '' });
  const [parts, setParts] = useState<Part[]>([blank()]);
  const [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { setErr(''); }, [resched?.id]);
  const set = (i: number, k: keyof Part, v: string) => { setErr(''); setParts(parts.map((p, j) => (j === i ? { ...p, [k]: v } : p))); };
  const len = (p: Part) => (p.start && p.end && p.end >= p.start ? days(p.start, p.end) : 0);
  const filled = parts.filter((p) => len(p) > 0);
  const total = filled.reduce((s, p) => s + len(p), 0);
  const ready = parts.every((p) => p.start && p.end);
  const sorted = [...filled].sort((a, b) => a.start.localeCompare(b.start));
  const overlap = sorted.some((p, i) => i > 0 && p.start <= sorted[i - 1].end);
  const touched = filled.length > 0;

  const submit = async () => {
    setBusy(true); setErr('');
    try { await onSubmit(parts); setParts([blank()]); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <section className={`panel form${resched ? ' resched' : ''}`} aria-label="Заявка на отпуск">
      <div className="panel-head">
        <h2>{resched ? `Перенос заявки №${resched.id}` : 'Новая заявка'}</h2>
        {resched && <button className="btn ghost" onClick={onStopResched}>Не переносить</button>}
      </div>
      <p className="muted">{resched
        ? `Сейчас отпуск: ${dates(resched)}. Старая заявка отменится, новая уйдёт на согласование.`
        : approvers.length ? `Заявку согласует ${approvers.map(short).join(' или ')}. Отпуск можно разбить на части.`
          : 'Согласовать заявку некому: у вас не назначен руководитель. Обратитесь в HR.'}</p>
      {parts.map((p, i) => (
        <div className="part" key={i}>
          <div className="field"><label htmlFor={`s${i}`}>{parts.length > 1 ? `Часть ${i + 1}: с` : 'С'}</label>
            <input id={`s${i}`} type="date" min={today} value={p.start} onChange={(e) => set(i, 'start', e.target.value)} /></div>
          <div className="field"><label htmlFor={`e${i}`}>По</label>
            <input id={`e${i}`} type="date" min={p.start || today} value={p.end} onChange={(e) => set(i, 'end', e.target.value)} /></div>
          <span className={`len${len(p) ? ' on' : ''}`}>{len(p) ? daysLabel(len(p)) : ''}</span>
          {parts.length > 1 && <button className="btn icon" aria-label={`Убрать часть ${i + 1}`} onClick={() => setParts(parts.filter((_, j) => j !== i))}><Icon name="x" /></button>}
        </div>
      ))}
      <ul className="checks" aria-label="Правила дробления">
        <Check ok={touched ? filled.some((p) => len(p) >= 14) : null}>Одна часть от 14 дней</Check>
        <Check ok={touched ? filled.every((p) => len(p) >= 5) : null}>Остальные от 5 дней</Check>
        <Check ok={touched ? !overlap : null}>Части не пересекаются</Check>
        {!resched && <Check ok={touched ? total <= free : null}>{`Свободно сейчас ${daysLabel(free)}`}</Check>}
      </ul>
      {err && <div className="alert" role="alert">{err}</div>}
      <div className="actions">
        <button className="btn ghost" disabled={parts.length >= 3} onClick={() => setParts([...parts, blank()])}><Icon name="plus" />Добавить часть</button>
        <span className="total">{total ? `Всего ${daysLabel(total)}` : ''}</span>
        <button className="btn primary" disabled={!ready || busy} onClick={submit}>{resched ? 'Отправить перенос' : 'Отправить на согласование'}</button>
      </div>
      <p className="fine">До трёх частей в заявке и не больше четырёх частей за календарный год. Окончательно правила и накопление проверяет сервер.</p>
    </section>
  );
}

function History({ v }: { v: Vac }) {
  const bits: string[] = [];
  if (v.created_at) bits.push(`подана ${whenShort(v.created_at)}`);
  if (v.replaces_id) bits.push(`перенос заявки №${v.replaces_id}`);
  if (v.decided_at && v.decided_by_name) bits.push(`${v.status === 'rejected' ? 'отклонил' : 'согласовал'} ${short(v.decided_by_name)} ${whenShort(v.decided_at)}`);
  if (v.cancelled_on) bits.push(`отменена ${dayMonth(v.cancelled_on)}`);
  return bits.length ? <span className="history">{bits.join(', ')}</span> : null;
}

export function MyRequests({ me, vac, onCancel, onResched }: { me: Me; vac: Vac[]; onCancel: (v: Vac) => void; onResched: (v: Vac) => void }) {
  const mine = vac.filter((v) => v.user_id === me.id);
  return (
    <section className="panel" aria-label="Мои заявки">
      <h2>Мои заявки</h2>
      {mine.length === 0 ? <Empty title="Заявок пока нет">Выберите даты в форме выше и отправьте заявку на согласование.</Empty> : (
        <ul className="list">{mine.map((v) => (
          <li key={v.id} className={`item st-${v.status}`}>
            <div className="item-main">
              <b className="dates">{dates(v)}</b>
              <span className="muted">{daysLabel(v.days)}, заявка №{v.id}</span>
              <History v={v} />
              {v.comment && <span className={v.status === 'rejected' ? 'why' : 'muted'}>{v.status === 'rejected' ? 'Причина отказа' : 'Комментарий'}: {v.comment}</span>}
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

/* ---------- Согласование ---------- */

function Decision({ v, onDecide }: { v: Vac; onDecide: (v: Vac, approve: boolean, comment?: string) => Promise<void> }) {
  const [rejecting, setRejecting] = useState(false), [reason, setReason] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  const run = (approve: boolean) => { setBusy(true); onDecide(v, approve, reason).catch((e) => setErr((e as Error).message)).finally(() => setBusy(false)); };
  return (
    <li className="item col st-pending">
      <div className="item-top">
        <Avatar name={v.name} />
        <div className="item-main">
          <b>{short(v.name)}</b>
          <span>{dates(v)}</span>
          <span className="muted">{daysLabel(v.days)}, заявка №{v.id}{v.replaces_id ? `, перенос заявки №${v.replaces_id}` : ''}</span>
          {v.balance_after !== undefined && <span className="muted">Свободно у сотрудника с учётом заявки: {daysLabel(v.balance_after)}</span>}
        </div>
        <StatusChip s={v.status} />
      </div>
      {v.conflicts && v.conflicts.length > 0 && (
        <div className="warn" role="note"><b>Пересекается с отпуском в команде:</b>{' '}
          {v.conflicts.map((c) => `${short(c.name)}, ${range(c.start, c.end)}`).join('; ')}</div>)}
      {rejecting ? (
        <div className="reject">
          <label htmlFor={`r${v.id}`}>Причина отказа</label>
          <textarea id={`r${v.id}`} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: в эти даты релиз" autoFocus />
          {err && <div className="alert" role="alert">{err}</div>}
          <div className="actions">
            <button className="btn ghost" onClick={() => { setRejecting(false); setErr(''); }}>Назад</button>
            <button className="btn danger solid" disabled={!reason.trim() || busy} onClick={() => run(false)}>Отклонить заявку</button>
          </div>
        </div>
      ) : (
        <div className="actions">
          {err && <div className="alert" role="alert">{err}</div>}
          <button className="btn ghost" onClick={() => setRejecting(true)}>Отклонить</button>
          <button className="btn primary" disabled={busy} onClick={() => run(true)}><Icon name="check" />Согласовать</button>
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
      {wait.length === 0 ? <Empty title="Новых заявок нет">Когда сотрудник отправит заявку, она появится здесь без перезагрузки страницы.</Empty>
        : <ul className="list">{wait.map((v) => <Decision key={v.id} v={v} onDecide={onDecide} />)}</ul>}
    </section>
    {done.length > 0 && (
      <section className="panel" aria-label="Принятые решения">
        <h2>Уже рассмотрено</h2>
        <ul className="list">{done.map((v) => (
          <li key={v.id} className={`item st-${v.status}`}>
            <Avatar name={v.name} />
            <div className="item-main"><b>{short(v.name)}</b><span className="dates">{dates(v)}</span>
              <span className="muted">{daysLabel(v.days)}, заявка №{v.id}</span>
              <History v={v} />
              {v.comment && <span className="muted">Комментарий: {v.comment}</span>}</div>
            <StatusChip s={v.status} />
          </li>))}</ul>
      </section>)}
  </>);
}

/* ---------- HR ---------- */

function HrRow({ u, today, save }: { u: HrUser; today: string; save: (hd: string) => Promise<void> }) {
  const [hd, setHd] = useState(u.hire_date), [busy, setBusy] = useState(false);
  useEffect(() => setHd(u.hire_date), [u.hire_date]);
  const changed = hd !== u.hire_date && !!hd;
  return (
    <tr className={u.needsAttention ? 'attn' : ''}>
      <td><div className="who-cell"><Avatar name={u.name} /><div><b>{short(u.name)}</b>
        <span className="muted block">{u.manager ? `${u.team}, руководитель ${short(u.manager)}` : u.team}</span></div></div></td>
      <td><div className="inline"><input aria-label={`Дата выхода: ${u.name}`} type="date" max={today} value={hd} onChange={(e) => setHd(e.target.value)} />
        {changed && <button className="btn primary sm" disabled={busy} onClick={() => { setBusy(true); save(hd).finally(() => setBusy(false)); }}>Сохранить</button>}</div></td>
      <td className="num">{u.accrued}</td>
      <td className="num">{u.used}</td>
      <td className="num">{u.planned}</td>
      <td className="num"><b>{u.free}</b></td>
      <td>{u.needsAttention
        ? <><span className="chip chip-pending">Проверить заявки</span>{u.problem && <span className="muted block problem">{u.problem}</span>}</>
        : u.onVacation ? <span className="chip chip-approved">В отпуске</span> : <span className="muted">В порядке</span>}</td>
    </tr>
  );
}

export function HrOverview({ users, cal, today, onSaveHire }: { users: HrUser[]; cal: CalRow[]; today: string; onSaveHire: (u: HrUser, hd: string) => Promise<void> }) {
  const away = users.filter((u) => u.onVacation).length;
  const pending = new Set(cal.filter((r) => r.status === 'pending').map((r) => r.id)).size;
  const soon = new Set(cal.filter((r) => r.status === 'approved' && r.start > today && r.start <= addDays(today, 14)).map((r) => r.name)).size;
  const attention = users.filter((u) => u.needsAttention).length;
  return (<>
    <div className="stats">
      <div className="stat"><b>{away}</b><span>в отпуске сегодня из {users.length}</span></div>
      <div className="stat"><b>{soon}</b><span>уходят в отпуск в ближайшие 2 недели</span></div>
      <div className="stat"><b>{pending}</b><span>{pending === 1 ? 'заявка ждёт' : 'заявок ждут'} согласования</span></div>
      <div className={`stat${attention ? ' alert-stat' : ''}`}><b>{attention}</b><span>требуют проверки после смены даты выхода</span></div>
    </div>
    <section className="panel" aria-label="Остатки по сотрудникам">
      <h2>Остатки по сотрудникам</h2>
      <p className="muted">Измените дату выхода на работу, и накопление пересчитается у всех сразу. «Можно взять» учитывает уже поданные заявки.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Сотрудник</th><th>Дата выхода</th><th className="num">Накоплено</th><th className="num">Использовано</th><th className="num">В заявках</th><th className="num">Можно взять</th><th>Состояние</th></tr></thead>
        <tbody>{users.map((u) => <HrRow key={u.id} u={u} today={today} save={(hd) => onSaveHire(u, hd)} />)}</tbody>
      </table></div>
    </section>
  </>);
}
