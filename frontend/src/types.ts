export type Status = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type Role = 'employee' | 'manager' | 'hr';
export interface Part { start: string; end: string }
export interface Me { id: number; name: string; role: Role; team: string; hire_date: string; today: string; approvers: string[] }
export interface Conflict { name: string; start: string; end: string }
export interface Vac {
  id: number; status: Status; comment: string | null; user_id: number; name: string; team: string; parts: Part[]; days: number;
  created_at: string | null; decided_at: string | null; decided_by_name: string | null; cancelled_on: string | null; replaces_id: number | null;
  conflicts?: Conflict[]; balance_after?: number;
}
export interface Balance { date: string; annual: number; accrued: number; used: number; reserved: number; planned: number; available: number; free: number }
export interface CalRow { id: number; status: Status; name: string; team: string; start: string; end: string }
export interface Note { id: number; type: string; text: string; created_at: string; read_at: string | null }
export interface HrUser {
  id: number; name: string; team: string; role: Role; manager: string | null; hire_date: string;
  accrued: number; used: number; planned: number; free: number; available: number; onVacation: boolean; needsAttention: boolean; problem: string | null;
}
export interface Health { status: string; db: string; warning: string | null }
export interface Data { bal: Balance; fc: Balance; vac: Vac[]; cal: CalRow[]; notes: Note[]; hr: HrUser[] }
