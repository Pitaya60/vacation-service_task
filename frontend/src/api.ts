export const API: string = import.meta.env.VITE_API ?? 'http://localhost:8000/api/v1';
let token = sessionStorage.getItem('vac_token') ?? '';

export class AuthError extends Error {}
export const hasToken = () => !!token;
export const getToken = () => token;
export const setToken = (t: string) => { token = t; t ? sessionStorage.setItem('vac_token', t) : sessionStorage.removeItem('vac_token'); };

export async function call<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch(API + path, {
    method, headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => { throw new Error(`Нет связи с сервером. Проверьте, что backend запущен: ${API}/health`); });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = j.error || r.statusText;
    if (r.status === 401 && path !== '/login') throw new AuthError(msg);
    throw new Error(msg);
  }
  return j as T;
}
