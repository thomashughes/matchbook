import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthShell from './AuthShell';
import { useAuth } from '@/hooks/useAuth';
import { ApiError } from '@/api/client';

/**
 * Consume a password-reset token and set a new password.
 * Token arrives via ?token= in the email link.
 */
export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { resetPassword } = useAuth();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) return setError('Passwords do not match');
    if (password.length < 8) return setError('Password must be at least 8 characters');
    setSubmitting(true);
    try {
      await resetPassword(token, password);
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
        title="Password updated"
        subtitle="You can now sign in with your new password."
        footer={
          <Link to="/login" className="text-rust hover:underline">
            Go to sign in →
          </Link>
        }
      >
        <div className="text-sm text-ink-2 bg-teal-light rounded-lg px-3 py-3">
          Your account is also now verified.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Set a new password" subtitle="Make it a good one.">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-label" htmlFor="password">New password</label>
          <input
            id="password" className="mb-input" type="password" required autoComplete="new-password"
            minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-label" htmlFor="confirm">Confirm new password</label>
          <input
            id="confirm" className="mb-input" type="password" required autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        {error && (
          <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-2">{error}</div>
        )}

        <button className="mb-btn-primary w-full" disabled={submitting || !token}>
          {submitting ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </AuthShell>
  );
}
