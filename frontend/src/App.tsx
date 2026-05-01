/**
 * Route tree.
 *
 * Auth routes render bare; every authenticated page renders inside
 * AppShell so the sidebar/topbar and the quick-add panel context are
 * always mounted. Onboarding routes deliberately skip AppShell — we
 * want the focused, full-bleed layout until the user has a profile.
 *
 * Boot sequence: on mount we attempt one silent refresh against the
 * httpOnly refresh cookie. If it succeeds we hydrate the auth store
 * before any route guard fires; if it fails we fall through to the
 * normal "log in again" path. Route guards wait on `bootstrapped` so
 * a cold load never flashes the login page for an already-signed-in
 * user.
 */
import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import NotFoundPage from './pages/NotFoundPage';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import VerifyEmailPage from './pages/auth/VerifyEmailPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';
import ResetPasswordPage from './pages/auth/ResetPasswordPage';
import { CVUploadPage } from './pages/onboarding/CVUploadPage';
import { QuestionsPage } from './pages/onboarding/QuestionsPage';
import { DonePage } from './pages/onboarding/DonePage';
import { DashboardPage } from './pages/DashboardPage';
import { JobsPage } from './pages/JobsPage';
import { JobDetailPage } from './pages/JobDetailPage';
import { ProfilePage } from './pages/ProfilePage';
import { BillingPage } from './pages/BillingPage';
import { CvBuilderPage } from './pages/CvBuilderPage';
import { AppShell } from './components/layout/AppShell';
import { useAuthStore } from './stores/auth';
import { useProfile } from './api/hooks';
import { api, tryRefresh } from './api/client';
import type { ReactNode } from 'react';

interface UserResponse {
  id: string;
  email: string;
  is_verified: boolean;
}

/**
 * One-shot boot bootstrapper. Calls /auth/refresh; on success populates
 * the user via /auth/me. Either way flips `bootstrapped` so the route
 * guards stop showing the splash. We swallow errors — bootstrap should
 * never throw to the UI; "no session" is a valid outcome.
 */
function useAuthBootstrap() {
  const setUser = useAuthStore((s) => s.setUser);
  const setBootstrapped = useAuthStore((s) => s.setBootstrapped);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await tryRefresh();
        if (!cancelled && token) {
          // /auth/me uses the freshly-set bearer; safe to call via the
          // normal api() wrapper.
          const me = await api<UserResponse>('/auth/me');
          if (!cancelled) setUser(me);
        }
      } catch {
        /* No session, expired refresh cookie, or backend hiccup — fall
           through to the unauth path. */
      } finally {
        if (!cancelled) setBootstrapped(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setUser, setBootstrapped]);
}

/**
 * Centred splash shown for the brief window between mount and the boot
 * refresh resolving. Deliberately unbranded and minimal — anything more
 * elaborate gets seen as a "loading screen" by users on slow networks.
 */
function BootSplash() {
  return (
    <div className="min-h-full flex items-center justify-center bg-cream">
      <div className="text-ink-3 text-sm">Loading…</div>
    </div>
  );
}

function Protected({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.accessToken);
  const bootstrapped = useAuthStore((s) => s.bootstrapped);
  // Wait for the boot-time refresh to settle before deciding. Without
  // this gate a hard load races the refresh and the user sees /login
  // for ~50ms even though their session is valid.
  if (!bootstrapped) return <BootSplash />;
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

/**
 * Gate for the authenticated app. Why: a user with no profile has
 * nothing meaningful to see on the dashboard/jobs pages — we force
 * them through onboarding first. The API returns 404 on /profile
 * before onboarding completes; useProfile({ retry: false }) surfaces
 * that as isError, which we treat as the "needs onboarding" signal.
 */
function RequireProfile({ children }: { children: ReactNode }) {
  const { isLoading, isError } = useProfile();
  if (isLoading) return null;
  if (isError) return <Navigate to="/onboarding/cv" replace />;
  return <>{children}</>;
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <Protected>
      <RequireProfile>
        <AppShell>{children}</AppShell>
      </RequireProfile>
    </Protected>
  );
}

export default function App() {
  useAuthBootstrap();

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route path="/onboarding/cv" element={<Protected><CVUploadPage /></Protected>} />
      <Route path="/onboarding/questions" element={<Protected><QuestionsPage /></Protected>} />
      <Route path="/onboarding/done" element={<Protected><DonePage /></Protected>} />

      <Route path="/" element={<Shell><DashboardPage /></Shell>} />
      <Route path="/jobs" element={<Shell><JobsPage /></Shell>} />
      <Route path="/jobs/:id" element={<Shell><JobDetailPage /></Shell>} />
      <Route path="/profile" element={<Shell><ProfilePage /></Shell>} />
      <Route path="/billing" element={<Shell><BillingPage /></Shell>} />
      <Route path="/cv" element={<Shell><CvBuilderPage /></Shell>} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
