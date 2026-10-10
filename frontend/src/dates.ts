const parse = (s: string) => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); };
const iso = (d: Date) => d.toISOString().slice(0, 10);

export const days = (a: string, b: string) => Math.round((parse(b).getTime() - parse(a).getTime()) / 864e5) + 1;
export const addDays = (s: string, n: number) => iso(new Date(parse(s).getTime() + n * 864e5));
export const dayMonth = (s: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(parse(s)).replace('.', '');
export const full = (s: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parse(s));
export const monthTitle = (ym: string) => { const t = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parse(ym + '-01')).replace(' г.', ''); return t[0].toUpperCase() + t.slice(1); };
export const range = (a: string, b: string) =>
  a.slice(0, 4) === b.slice(0, 4) ? `${dayMonth(a)} – ${dayMonth(b)} ${b.slice(0, 4)}` : `${dayMonth(a)} ${a.slice(0, 4)} – ${dayMonth(b)} ${b.slice(0, 4)}`;
export const shiftMonth = (ym: string, k: number) => { const [y, m] = ym.split('-').map(Number); return iso(new Date(Date.UTC(y, m - 1 + k, 1))).slice(0, 7); };
export const monthDays = (ym: string) => { const [y, m] = ym.split('-').map(Number); return new Date(Date.UTC(y, m, 0)).getUTCDate(); };
export const isWeekend = (s: string) => [0, 6].includes(parse(s).getUTCDay());
export const plural = (n: number, [one, few, many]: [string, string, string]) => {
  const a = Math.abs(n) % 100, b = a % 10;
  return a > 10 && a < 20 ? many : b > 1 && b < 5 ? few : b === 1 ? one : many;
};
export const daysLabel = (n: number) => `${n} ${plural(n, ['день', 'дня', 'дней'])}`;

/** Метка времени из БД: PostgreSQL отдаёт ISO с часовым поясом, SQLite — «YYYY-MM-DD HH:MM:SS» в UTC. */
export const stamp = (s: string) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s.replace(' ', 'T') + 'Z');
export const ago = (s: string, now = Date.now()) => {
  const m = Math.round((now - stamp(s).getTime()) / 60000);
  if (m < 1) return 'только что';
  if (m < 60) return `${m} мин назад`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} ч назад`;
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(stamp(s)).replace('.', '');
};
export const whenShort = (s: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(stamp(s)).replace('.', '');
