/**
 * Auth store — in-memory only, by design.
 *
 * The access token MUST NOT be persisted to localStorage or sessionStorage.
 * If persisted, an XSS payload can trivially exfiltrate it; in memory,
 * it dies when the tab closes and is significantly harder to steal.
 *
 * The consequence is that a full page refresh "logs the user out" — until
 * the next API call triggers the silent refresh in client.ts, which
 * exchanges the still-valid httpOnly refresh cookie for a new access
 * token. Net UX: indistinguishable from persistence, safer by default.
 */
import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  user: { id: string; email: string; is_verified: boolean } | null;
  setAccessToken: (token: string | null) => void;
  setUser: (user: AuthState['user']) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  setAccessToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user }),
  clear: () => set({ accessToken: null, user: null }),
}));
