import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import AuthShell from './AuthShell';
import { useAuth } from '@/hooks/useAuth';

/**
 * Forgot-password request page.
 * Always shows the same confirmation regardless of whether the email
 * exists (enumeration resistance — matches backend behaviour).
 */
export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await forgotPassword(email);
    } finally {
      // Whether or not the server "succeeded", we show the same result —
      // we're mirroring the server's privacy-preserving behaviour.
      setDone(true);
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthShell
        title="Check your inbox"
        subtitle="If that account exists, we've sent a reset link."
        footer={
          <Link to="/login" className="text-rust hover:underline">
            Back to sign in
          </Link>
        }
      >
        <div className="text-sm text-ink-2 bg-teal-light rounded-lg px-3 py-3">
          The link expires in 1 hour for your security.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email — we'll send you a link."
      footer={
        <Link to="/login" className="text-rust hover:underline">
          Back to sign in
        </Link>
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
        <button className="mb-btn-primary w-full" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </AuthShell>
  );
}
