/**
 * TopBar — wordmark on the left, actions on the right.
 * Quick-add job button is the primary action — matches §3.7 dashboard spec.
 *
 * Also surfaces a "Continue onboarding" nudge when the user's profile
 * isn't complete — we show it on the LEFT so it sits in the primary
 * reading path, not hidden next to the avatar.
 */
import { ArrowRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { useProfile } from '@/api/hooks';
import { UsagePill } from './UsagePill';

export function TopBar({ onQuickAdd }: { onQuickAdd: () => void }) {
  const user = useAuthStore((s) => s.user);
  const initial = user?.email?.[0]?.toUpperCase() ?? '?';
  // Profile query: if isError (404 from backend) the user has no
  // profile yet — AppShell already routes them to /onboarding/cv in
  // that case, so we don't show the banner here.
  // If the profile exists but onboarding_complete is false, the user
  // has uploaded a CV but never answered the clarifying questions;
  // that's exactly who this banner is for.
  const prof = useProfile();
  const showContinue =
    prof.data && prof.data.onboarding_complete === false;

  return (
    <header
      className="sticky top-0 z-20 bg-cream/90 backdrop-blur hidden md:flex items-center justify-between px-7 h-14"
      style={{ borderBottom: '0.5px solid var(--border)' }}
    >
      <div>
        {showContinue && (
          <Link
            to="/onboarding/questions"
            className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full transition hover:opacity-90"
            style={{
              background: 'var(--rust-light, #f7e3d9)',
              color: 'var(--rust, #b0552d)',
            }}
          >
            Finish onboarding
            <ArrowRight size={12} />
          </Link>
        )}
      </div>
      <div className="flex items-center gap-3">
        {/* UsagePill sits to the left of Add Job so "X of Y jobs" is the
            first thing the user sees when their eye travels to the
            creation action. Clicking it goes to /billing. */}
        <UsagePill />
        <button className="mb-btn-primary !py-2" onClick={onQuickAdd}>
          <Plus size={16} />
          Add job
        </button>
        <div
          className="w-8 h-8 rounded-full bg-parchment text-ink flex items-center justify-center font-medium text-sm"
          title={user?.email ?? ''}
        >
          {initial}
        </div>
      </div>
    </header>
  );
}
