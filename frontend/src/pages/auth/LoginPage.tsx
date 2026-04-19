import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell from './AuthShell';
import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/auth';
import { ApiError } from '@/api/client';

/**
 * Login page.
 *
 * UX notes:
 *   - Error messaging intentionally generic ("Invalid credentials") to
 *     match the backend's enumeration-resistant response.
 *   - Submit button shows an inline "Signing in…" state rather than a
 *     blank spinner (handoff §7.4 — never leave the user uncertain).
 */
export default function LoginPage() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      nav('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to continue your search."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="text-rust hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-label" htmlFor="email">Email</label>
          <input
            id="email"
            className="mb-input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-label" htmlFor="password">Password</label>
          <input
            id="password"
            className="mb-input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="mt-2 text-right">
            <Link to="/forgot-password" className="text-sm text-ink-3 hover:text-rust">
              Forgot password?
            </Link>
          </div>
        </div>

        {error && (
          <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-2">{error}</div>
        )}

        <button className="mb-btn-primary w-full" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>

        {/*
          Dev-only bypass: lets us preview the dashboard without a running
          backend. Populates the Zustand store with a fake token + user so
          the route guard in App.tsx lets us through. Gated on DEV so it
          is tree-shaken out of production builds.
        */}
        {import.meta.env.DEV && (
          <button
            type="button"
            className="mb-btn-ghost w-full border border-dashed border-border"
            onClick={() => {
              useAuthStore.getState().setAccessToken('dev-preview');
              useAuthStore.getState().setUser({
                id: 'dev-preview',
                email: 'preview@matchbook.local',
                is_verified: true,
              });
              nav('/');
            }}
          >
            Skip login (dev preview)
          </button>
        )}
      </form>
    </AuthShell>
  );
}
