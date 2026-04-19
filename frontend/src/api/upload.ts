/**
 * Multipart upload helper — separate from api() because multipart/form-data
 * must NOT set Content-Type manually (the browser writes the boundary).
 * Keeps the happy-path client.ts tight and focused on JSON.
 */
import { useAuthStore } from '@/stores/auth';
import { ApiError } from './client';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export async function uploadFile<T>(path: string, file: File, field = 'file'): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  const form = new FormData();
  form.append(field, file);

  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
