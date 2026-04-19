/**
 * Thin auth actions layer. Wraps the API client + store so pages don't
 * have to know the wire shape.
 */
import { api } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

interface TokenResponse {
  access_token: string;
  expires_in_seconds: number;
}

interface UserResponse {
  id: string;
  email: string;
  is_verified: boolean;
}

export function useAuth() {
  const { setAccessToken, setUser, clear } = useAuthStore();

  return {
    async login(email: string, password: string) {
      const tok = await api<TokenResponse>('/auth/login', {
        method: 'POST',
        body: { email, password },
        skipAuthRefresh: true,
      });
      setAccessToken(tok.access_token);
      const me = await api<UserResponse>('/auth/me');
      setUser(me);
    },

    async register(email: string, password: string) {
      await api<{ message: string }>('/auth/register', {
        method: 'POST',
        body: { email, password },
        skipAuthRefresh: true,
      });
    },

    async verifyEmail(token: string) {
      await api<{ message: string }>('/auth/verify-email', {
        method: 'POST',
        body: { token },
        skipAuthRefresh: true,
      });
    },

    async forgotPassword(email: string) {
      await api<{ message: string }>('/auth/forgot-password', {
        method: 'POST',
        body: { email },
        skipAuthRefresh: true,
      });
    },

    async resetPassword(token: string, newPassword: string) {
      await api<{ message: string }>('/auth/reset-password', {
        method: 'POST',
        body: { token, new_password: newPassword },
        skipAuthRefresh: true,
      });
    },

    async logout() {
      try {
        await api('/auth/logout', { method: 'POST', skipAuthRefresh: true });
      } finally {
        // Always clear local state, even if the network call failed —
        // the user asked to log out, honour that UX promise.
        clear();
      }
    },
  };
}
