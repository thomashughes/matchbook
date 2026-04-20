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
  // data holds the full backend detail payload when it's an object,
  // which 402 quota responses always are. For string-detail errors
  // (most 4xx/5xx) data is null and `detail` is the user-facing
  // message.
  constructor(
    public status: number,
    public detail: string,
    public data: unknown = null,
  ) {
    super(detail);
  }
}

/**
 * Shape of the 402 body emitted by backend QuotaExceeded.
 *
 * Mirrored from `core/entitlements.py: QuotaExceeded.__init__`. Keep
 * in sync if the backend field names change.
 */
export interface QuotaErrorDetail {
  error: 'quota_exceeded';
  resource: string;
  limit: number;
  used: number;
  resets_at: string;
  upgrade_url: string;
}

/**
 * Narrow an ApiError to a quota-exceeded error. UI components use
 * this to decide whether to render an upgrade CTA vs a generic
 * error toast.
 */
export function isQuotaError(
  err: unknown,
): err is ApiError & { data: QuotaErrorDetail } {
  return (
    err instanceof ApiError &&
    err.status === 402 &&
    typeof err.data === 'object' &&
    err.data !== null &&
    (err.data as { error?: unknown }).error === 'quota_exceeded'
  );
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
    // FastAPI returns { detail: string | object }. For most errors it's
    // a string ("Not found", "Not authenticated"). For 402 quota errors
    // the detail is an object carrying resource/limit/used/resets_at so
    // the UI can render a proper upgrade CTA. We preserve both: `detail`
    // is always a string for .message display, `data` is the full object
    // when present.
    let detail = res.statusText;
    let data: unknown = null;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body?.detail === 'string') {
        detail = body.detail;
      } else if (body?.detail && typeof body.detail === 'object') {
        data = body.detail;
        // Synthesise a human-readable message from the structured data
        // so callers that only look at .message still get something
        // useful to show.
        const d = body.detail as { error?: string; resource?: string };
        detail =
          d.error === 'quota_exceeded' && d.resource
            ? `Quota exceeded for ${d.resource}.`
            : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON body — use statusText */
    }
    throw new ApiError(res.status, detail, data);
  }

  // 204 No Content has no body to parse.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
