// Чистые правила предметной области (описаны в README). Даты — строки YYYY-MM-DD.
export const ANNUAL = 28;
export type Part = { start: string; end: string };
export const day = (s: string) => Date.parse(s + 'T00:00:00Z') / 86400000;
export const iso = (d: number) => new Date(d * 86400000).toISOString().slice(0, 10);
export const len = (p: Part) => day(p.end) - day(p.start) + 1;

/** Накоплено на дату: 28 * отработанные_дни / 365, вниз до целого. */
export const accrued = (hire: string, on: string) =>
  Math.max(0, Math.floor((ANNUAL * (day(on) - day(hire))) / 365));

export function validateParts(parts: Part[]): string | null {
  if (!parts.length) return 'В заявке нет ни одной части.';
  if (parts.length > 3) return 'Не более 3 частей в одной заявке.';
  if (parts.some((p) => !(len(p) >= 1))) return 'Дата окончания раньше даты начала.';
  const s = [...parts].sort((a, b) => day(a.start) - day(b.start));
  for (let i = 1; i < s.length; i++)
    if (day(s[i].start) <= day(s[i - 1].end)) return 'Части отпуска пересекаются.';
  if (!parts.some((p) => len(p) >= 14)) return 'В заявке нет части от 14 дней.';
  if (parts.some((p) => len(p) < 5)) return 'Каждая часть должна быть не короче 5 дней.';
  return null;
}

/** Нарастающий итог дней по хронологии не должен превышать накопленное к началу каждой части. */
export function checkBalance(hire: string, existing: Part[], added: Part[]): string | null {
  const all = [...existing, ...added].sort((a, b) => day(a.start) - day(b.start));
  let cum = 0;
  for (const p of all) {
    cum += len(p);
    const a = accrued(hire, p.start);
    if (cum > a) return `К ${p.start} накоплено ${a} дн., а с этой заявкой потребуется ${cum} дн.`;
  }
  return null;
}
