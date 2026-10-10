import type { ReactNode } from 'react';
import type { Status } from './types';

const LABEL: Record<Status, string> = { pending: 'На рассмотрении', approved: 'Согласован', rejected: 'Отклонён', cancelled: 'Отменён' };
export const statusLabel = (s: Status) => LABEL[s];
export const short = (name: string) => name.replace(/\s*\(.*\)\s*$/, '');
export const initials = (name: string) => short(name).split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
export const StatusChip = ({ s }: { s: Status }) => <span className={`chip chip-${s}`}>{LABEL[s]}</span>;

export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="empty"><b>{title}</b>{children && <p>{children}</p>}</div>
);

const PATHS = {
  bell: 'M12 3a6 6 0 0 0-6 6v3.5L4 16v1h16v-1l-2-3.5V9a6 6 0 0 0-6-6Zm-2 16a2 2 0 0 0 4 0',
  plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6 6 18', left: 'M15 5l-7 7 7 7', right: 'M9 5l7 7-7 7',
  check: 'M5 12.5l4.5 4.5L19 7', dot: 'M12 12h.01', warn: 'M12 8v5M12 16.5h.01M10.3 3.9 2.6 17.3A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0Z',
  logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3',
} as const;
export type IconName = keyof typeof PATHS;

export const Icon = ({ name, size = 18 }: { name: IconName; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]} /></svg>
);

export const Logo = () => (
  <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
    <circle className="logo-sun" cx="16" cy="16" r="15" />
    <path d="M1 20c5-6 9-6 15 0s10 6 15 0v1c0 6.600-6.700 11-15 11S1 27.600 1 21Z" fill="var(--blue)" />
  </svg>
);

export const Avatar = ({ name }: { name: string }) => <span className="avatar" aria-hidden="true">{initials(name)}</span>;
