import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/auth';

/**
 * Placeholder dashboard for Phase 1.
 *
 * Proves the full auth loop works end-to-end: a logged-in user sees their
 * email (from /auth/me), and the logout button clears the refresh cookie
 * + in-memory token. Phase 2 replaces this with the real dashboard and
 * onboarding flow.
 */
export default function DashboardStub() {
  const { logout } = useAuth();
  const user = useAuthStore((s) => s.user);

  return (
    <div className="min-h-full flex items-center justify-center bg-cream p-6">
      <div className="w-full max-w-lg mb-card">
        <div className="mb-display text-2xl text-ink">You're signed in</div>
        <p className="text-ink-2 mt-2">
          Hello{user ? `, ${user.email}` : ''}. Phase 1 is live — auth, database, Docker stack.
          The real dashboard ships in Phase 2.
        </p>
        <button onClick={logout} className="mb-btn-primary mt-5">
          Sign out
        </button>
      </div>
    </div>
  );
}
