import type { ReactNode } from 'react';
import type { Status } from './types';

const LABEL: Record<Status, string> = { pending: 'На рассмотрении', approved: 'Согласован', rejected: 'Отклонён', cancelled: 'Отменён' };
export const short = (name: string) => name.replace(/\s*\(.*\)\s*$/, '');
export const StatusChip = ({ s }: { s: Status }) => <span className={`chip chip-${s}`}>{LABEL[s]}</span>;

export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="empty"><b>{title}</b>{children && <p>{children}</p>}</div>
);

export const Icon = ({ name }: { name: 'bell' | 'plus' | 'x' | 'left' | 'right' }) => {
  const d = {
    bell: 'M12 3a6 6 0 0 0-6 6v3.5L4 16v1h16v-1l-2-3.5V9a6 6 0 0 0-6-6Zm-2 16a2 2 0 0 0 4 0',
    plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6 6 18', left: 'M15 5l-7 7 7 7', right: 'M9 5l7 7-7 7',
  }[name];
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
};

export const Logo = () => (
  <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
    <circle className="logo-sun" cx="16" cy="16" r="15" />
    <path d="M1 20c5-6 9-6 15 0s10 6 15 0v1c0 6.600-6.700 11-15 11S1 27.600 1 21Z" fill="var(--blue)" />
  </svg>
);
