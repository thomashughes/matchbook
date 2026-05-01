/**
 * NotFoundPage — friendly 404.
 *
 * Stands alone (no AppShell, no auth gate) so it can render regardless
 * of login state — a logged-out user hitting a stale link should still
 * get a real 404, not a redirect-bounce to /login. The CTA adapts: take
 * a signed-in user back to the dashboard, send everyone else to login.
 *
 * Style intentionally echoes AuthShell — same wordmark, same display
 * typeface, same cream/parchment palette — so the page reads as part of
 * Matchbook rather than a generic browser error screen.
 */
import { Link } from 'react-router-dom';
import { Compass, Sparkles } from 'lucide-react';
import { useAuthStore } from '@/stores/auth';

export default function NotFoundPage() {
  // Wait for the boot-time refresh to settle before deciding the CTA
  // copy — otherwise a signed-in user hitting a 404 via direct URL
  // would briefly see "Back to sign in" before the refresh resolves and
  // re-renders with the correct "Back to dashboard" label.
  const bootstrapped = useAuthStore((s) => s.bootstrapped);
  const isAuthed = useAuthStore((s) => Boolean(s.accessToken));
  const ctaTo = isAuthed ? '/' : '/login';
  const ctaLabel = isAuthed ? 'Back to dashboard' : 'Back to sign in';

  return (
    <div className="min-h-full flex items-center justify-center bg-cream px-4 py-10">
      <div className="w-full max-w-md text-center">
        <div className="inline-flex items-center gap-1.5 mb-8">
          <Sparkles size={18} className="text-rust" />
          <span className="mb-display text-2xl text-ink">Matchbook</span>
        </div>

        <div className="mb-card">
          {/* The compass icon does the visual lifting — "you've wandered
              off the map" — without needing decorative copy to spell it
              out. Sized generously so it reads on mobile too. */}
          <div
            className="mx-auto w-16 h-16 rounded-full flex items-center justify-center mb-5"
            style={{ background: 'var(--rust-light)' }}
          >
            <Compass size={28} className="text-rust" />
          </div>

          <div
            className="mb-display text-6xl mb-2 leading-none tabular-nums"
            style={{ color: 'var(--ink)' }}
          >
            404
          </div>
          <h1 className="mb-display text-xl text-ink mb-2">
            This page wandered off
          </h1>
          <p className="text-ink-2 text-sm leading-relaxed mb-6">
            The link's broken or the page has moved. It happens — let's
            get you back to somewhere useful.
          </p>

          {bootstrapped ? (
            <Link to={ctaTo} className="mb-btn-primary w-full">
              {ctaLabel}
            </Link>
          ) : (
            // Placeholder of equal height keeps the card from shifting
            // when the real CTA renders a moment later.
            <div className="mb-btn-primary w-full opacity-50 pointer-events-none">
              <span>Loading…</span>
            </div>
          )}
        </div>

        <p className="mt-5 text-xs text-ink-3">
          Still stuck? Email{' '}
          <a
            href="mailto:noreply@matchbook.tag-art.co.uk"
            className="underline hover:text-ink-2"
          >
            noreply@matchbook.tag-art.co.uk
          </a>
          .
        </p>
      </div>
    </div>
  );
}
