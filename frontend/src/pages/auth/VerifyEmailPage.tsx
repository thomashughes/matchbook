import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthShell from './AuthShell';
import { useAuth } from '@/hooks/useAuth';
import { ApiError } from '@/api/client';

/**
 * Email verification landing page.
 *
 * The verification email contains a link like
 *   {FRONTEND_URL}/verify-email?token=xxxxx
 * — we pull the token from the query string and POST it to the API.
 *
 * Three UI states: verifying, success, failure — each with a clear CTA
 * (handoff §7.4 empty states / micro-feedback rules). We never show a
 * silent spinner here.
 */
export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const { verifyEmail } = useAuth();
  const [state, setState] = useState<'verifying' | 'ok' | 'fail'>('verifying');
  const [error, setError] = useState<string>('Invalid or expired token');

  useEffect(() => {
    if (!token) {
      setState('fail');
      setError('No verification token provided');
      return;
    }
    verifyEmail(token)
      .then(() => setState('ok'))
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : 'Something went wrong');
        setState('fail');
      });
    // Intentionally no dep on verifyEmail — it's stable per render and
    // re-verifying would cause the token to be consumed twice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (state === 'verifying') {
    return (
      <AuthShell title="Verifying your email" subtitle="One moment…">
        <div className="text-sm text-ink-2">Checking your verification link.</div>
      </AuthShell>
    );
  }
  if (state === 'ok') {
    return (
      <AuthShell
        title="You're in"
        subtitle="Your email is verified. Time to find your next role."
        footer={
          <Link to="/login" className="text-rust hover:underline">
            Sign in →
          </Link>
        }
      >
        <div className="text-sm text-ink-2 bg-teal-light rounded-lg px-3 py-3">
          Account activated.
        </div>
      </AuthShell>
    );
  }
  return (
    <AuthShell
      title="We couldn't verify that link"
      subtitle="It may have expired or already been used."
      footer={
        <Link to="/register" className="text-rust hover:underline">
          Start over →
        </Link>
      }
    >
      <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-3">{error}</div>
    </AuthShell>
  );
}
