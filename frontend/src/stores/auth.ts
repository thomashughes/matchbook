/**
 * Auth store — in-memory only, by design.
 *
 * The access token MUST NOT be persisted to localStorage or sessionStorage.
 * If persisted, an XSS payload can trivially exfiltrate it; in memory,
 * it dies when the tab closes and is significantly harder to steal.
 *
 * On a hard load, the access token starts null. The boot sequence in
 * App.tsx attempts a silent refresh against the httpOnly refresh cookie
 * before the route guards run — that's why we track `bootstrapped`
 * explicitly. Without it, Protected would redirect to /login on every
 * cold load before the refresh has a chance to succeed.
 */
import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  user: { id: string; email: string; is_verified: boolean } | null;
  // True once the boot-time silent refresh attempt has settled (resolved
  // or failed). Route guards must wait on this before deciding whether
  // the user is authenticated, otherwise they'll race the refresh.
  bootstrapped: boolean;
  setAccessToken: (token: string | null) => void;
  setUser: (user: AuthState['user']) => void;
  setBootstrapped: (b: boolean) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  bootstrapped: false,
  setAccessToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user }),
  setBootstrapped: (bootstrapped) => set({ bootstrapped }),
  // clear() is called on logout. We deliberately leave bootstrapped
  // alone — the app has finished its boot sequence, and the user is now
  // simply unauthenticated. Resetting it would re-trigger the splash.
  clear: () => set({ accessToken: null, user: null }),
}));
