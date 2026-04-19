import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import AuthShell from './AuthShell';
import { useAuth } from '@/hooks/useAuth';
import { ApiError } from '@/api/client';

/**
 * Registration page.
 *
 * Matches the server's enumeration-resistant behaviour: we always show
 * the same "check your email" state on success — even if the address was
 * already registered. The user learns the truth when they attempt to
 * verify / log in.
 *
 * Password confirmation is client-only UX polish; it is NOT sent to the
 * server (no point — the server already validated length).
 */
export default function RegisterPage() {
  const { register } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setSubmitting(true);
    try {
      await register(email, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthShell
        title="Check your inbox"
        subtitle="We've sent a verification link. Click it to activate your account."
        footer={
          <>
            Already verified?{' '}
            <Link to="/login" className="text-rust hover:underline">
              Sign in
            </Link>
          </>
        }
      >
        <div className="text-sm text-ink-2 bg-teal-light rounded-lg px-3 py-3">
          If it doesn't arrive in a few minutes, check spam — and make sure the
          email you entered is correct.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Free to start. We'll take it from there."
      footer={
        <>
          Already have one?{' '}
          <Link to="/login" className="text-rust hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-label" htmlFor="email">Email</label>
          <input
            id="email" className="mb-input" type="email" required autoComplete="email"
            value={email} onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-label" htmlFor="password">Password</label>
          <input
            id="password" className="mb-input" type="password" required autoComplete="new-password"
            minLength={8}
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
          <p className="mt-1 text-xs text-ink-3">8 characters minimum.</p>
        </div>
        <div>
          <label className="mb-label" htmlFor="confirm">Confirm password</label>
          <input
            id="confirm" className="mb-input" type="password" required autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        {error && (
          <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-2">{error}</div>
        )}

        <button className="mb-btn-primary w-full" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  );
}
