/**
 * Lightweight fetch wrapper for the Matchbook API.
 *
 * Why hand-rolled fetch rather than axios:
 *   - We only need a small surface: JSON in, JSON out, bearer header,
 *     credentials:'include' for the refresh cookie.
 *   - Keeping the bundle lean matters for a showcase — axios is ~13kB gz.
 *
 * Auth model:
 *   - Access token lives in Zustand (in-memory only). NEVER in localStorage:
 *     XSS reading localStorage is the most common token-theft vector.
 *   - Refresh token lives in an httpOnly cookie set by the backend on
 *     /auth/login and /auth/refresh. We send it by always using
 *     credentials: 'include'.
 *
 * 401 handling:
 *   - On 401 we attempt ONE silent refresh via /auth/refresh. If that
 *     succeeds we replay the original request with the fresh token.
 *   - If refresh also fails, we clear the store and let the caller
 *     surface a "please log in again" state — the route guard will
 *     redirect to /login on the next render.
 */
import { useAuthStore } from '@/stores/auth';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  // Public endpoints (login, register) should not trigger the refresh
  // dance on 401 — there's nothing to refresh to.
  skipAuthRefresh?: boolean;
}

export class ApiError extends Error {
  // status lets callers render 401/403/429 UI differently from a 500.
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function rawFetch(path: string, opts: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(`${BASE}${path}`, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    // Required for the refresh cookie on /auth/refresh. Harmless on
    // other requests since the cookie is path-scoped to /auth.
    credentials: 'include',
  });
}

async function tryRefresh(): Promise<string | null> {
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { access_token: string };
  useAuthStore.getState().setAccessToken(data.access_token);
  return data.access_token;
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  let res = await rawFetch(path, opts, token);

  if (res.status === 401 && !opts.skipAuthRefresh) {
    const fresh = await tryRefresh();
    if (fresh) {
      res = await rawFetch(path, opts, fresh);
    } else {
      useAuthStore.getState().clear();
    }
  }

  if (!res.ok) {
    // The backend returns { detail: string } on errors (FastAPI default).
    // Fall back to statusText when the body isn't JSON (rare).
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      if (data?.detail) detail = data.detail;
    } catch {
      /* non-JSON body — use statusText */
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content has no body to parse.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
