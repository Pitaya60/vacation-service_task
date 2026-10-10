import { useState, type ReactNode } from 'react';
import type { CalRow } from './types';
import { dayMonth, daysLabel, days, isWeekend, monthDays, monthTitle, shiftMonth } from './dates';
import { Empty, Icon, short } from './ui';

interface Bar { row: CalRow; from: number; to: number }

export default function Calendar({ rows, today, byTeam = false }: { rows: CalRow[]; today: string; byTeam?: boolean }) {
  const [ym, setYm] = useState(today.slice(0, 7));
  const n = monthDays(ym);
  const first = `${ym}-01`, last = `${ym}-${String(n).padStart(2, '0')}`;
  const day = (i: number) => `${ym}-${String(i).padStart(2, '0')}`;

  // полосы, пересекающие выбранный месяц, по сотрудникам
  const people = new Map<string, { team: string; bars: Bar[] }>();
  for (const r of rows) {
    if (r.end < first || r.start > last) continue;
    const from = r.start < first ? 1 : Number(r.start.slice(8)), to = r.end > last ? n : Number(r.end.slice(8));
    const p = people.get(r.name) ?? { team: r.team, bars: [] };
    p.bars.push({ row: r, from, to });
    people.set(r.name, p);
  }
  const list = [...people.entries()].sort((a, b) => a[1].team.localeCompare(b[1].team) || a[0].localeCompare(b[0]));
  const todayIdx = today.slice(0, 7) === ym ? Number(today.slice(8)) : 0;
  const cells = Array.from({ length: n }, (_, i) => i + 1);

  const Track = ({ children }: { children?: ReactNode }) => (
    <div className="cal-track" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
      {cells.map((i) => <div key={i} style={{ gridColumn: i, gridRow: 1 }} className={`cal-cell${isWeekend(day(i)) ? ' we' : ''}${i === todayIdx ? ' today' : ''}`} />)}
      {children}
    </div>
  );

  let lastTeam = '';
  return (
    <section className="panel" aria-label="Календарь отпусков">
      <div className="cal-head">
        <div className="cal-nav">
          <button className="btn icon" aria-label="Предыдущий месяц" onClick={() => setYm(shiftMonth(ym, -1))}><Icon name="left" /></button>
          <h2>{monthTitle(ym)}</h2>
          <button className="btn icon" aria-label="Следующий месяц" onClick={() => setYm(shiftMonth(ym, 1))}><Icon name="right" /></button>
          {ym !== today.slice(0, 7) && <button className="btn ghost" onClick={() => setYm(today.slice(0, 7))}>К текущему месяцу</button>}
        </div>
        <div className="legend">
          <span><i className="sw sw-approved" />Согласован</span>
          <span><i className="sw sw-pending" />На рассмотрении</span>
          <span><i className="sw sw-today" />Сегодня</span>
        </div>
      </div>
      {list.length === 0 ? <Empty title="В этом месяце отпусков нет">Листайте месяцы стрелками. Календарь обновляется сам, когда кто-то подаёт или отменяет заявку.</Empty> : (
        <div className="cal-scroll"><div className="cal" style={{ minWidth: 150 + n * 24 }}>
          <div className="cal-row cal-days">
            <div className="cal-name" />
            <div className="cal-track" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
              {cells.map((i) => <div key={i} className={`cal-d${isWeekend(day(i)) ? ' we' : ''}${i === todayIdx ? ' today' : ''}`}>{i}</div>)}
            </div>
          </div>
          {list.map(([name, p]) => {
            const head = byTeam && p.team !== lastTeam ? (lastTeam = p.team, <div key={'t' + p.team} className="cal-team">{p.team}</div>) : null;
            return [head, (
              <div className="cal-row" key={name}>
                <div className="cal-name" title={name}>{short(name)}</div>
                <Track>
                  {p.bars.map((b) => (
                    <div key={b.row.id + '-' + b.row.start} className={`bar bar-${b.row.status}`} style={{ gridColumn: `${b.from} / ${b.to + 1}`, gridRow: 1 }}
                      title={`${short(name)}: ${dayMonth(b.row.start)} – ${dayMonth(b.row.end)}, ${daysLabel(days(b.row.start, b.row.end))}, ${b.row.status === 'approved' ? 'согласован' : 'на рассмотрении'}`}>
                      {b.to - b.from >= 3 && daysLabel(days(b.row.start, b.row.end))}
                    </div>
                  ))}
                </Track>
              </div>)];
          })}
        </div></div>
      )}
    </section>
  );
}
