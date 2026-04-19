/**
 * DashboardPage — landing after login.
 *
 * Surfaces three KPIs (best match, total jobs, interviews upcoming),
 * a list of the five highest-scoring recent jobs, and a prompt to
 * add a job if the list is empty. Onboarding redirect lives here:
 * if the user has no profile yet we bounce them to /onboarding/cv.
 */
import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Trophy, Briefcase, CalendarClock, Plus } from 'lucide-react';
import { useProfile, useJobs } from '@/api/hooks';
import { JobCard } from '@/components/ui/JobCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { useAppShell } from '@/components/layout/AppShell';

export function DashboardPage() {
  const nav = useNavigate();
  const profile = useProfile();
  const jobs = useJobs();
  const { openQuickAdd } = useAppShell();

  useEffect(() => {
    // Missing profile = hasn't finished onboarding. Route them there.
    if (profile.isSuccess && !profile.data) nav('/onboarding/cv', { replace: true });
  }, [profile.isSuccess, profile.data, nav]);

  const list = jobs.data ?? [];
  const topFive = [...list]
    .filter((j) => j.total_score != null)
    .sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0))
    .slice(0, 5);
  const best = topFive[0];
  const interviewCount = list.filter((j) => j.status === 'interviewing').length;

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-display text-3xl">
          {greeting()}, {(profile.data?.structured_data?.name as string | undefined)?.split(' ')[0] ?? 'there'}
        </div>
        <p className="text-sm text-ink-2 mt-1">Here's where things stand today.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Kpi
          icon={<Trophy size={18} className="text-gold" />}
          label="Best match"
          value={best ? `${best.total_score}%` : '—'}
          sub={best?.title ?? 'Add a job to get started'}
        />
        <Kpi
          icon={<Briefcase size={18} className="text-teal" />}
          label="Jobs tracked"
          value={String(list.length)}
          sub={list.length === 1 ? 'one so far' : ''}
        />
        <Kpi
          icon={<CalendarClock size={18} className="text-rust" />}
          label="Interviewing"
          value={String(interviewCount)}
          sub={interviewCount > 0 ? 'active conversations' : 'none right now'}
        />
      </div>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="mb-display text-lg">Top matches</h2>
          <Link to="/jobs" className="text-sm text-ink-2 hover:text-ink">View all →</Link>
        </div>
        {topFive.length === 0 ? (
          <EmptyState
            icon={Briefcase}
            title="No scored jobs yet"
            subtitle="Paste a job description and we'll tell you how well it fits."
            cta={
              <button className="mb-btn-primary" onClick={openQuickAdd}>
                <Plus size={16} /> Add a job
              </button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {topFive.map((j) => <JobCard key={j.id} job={j} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function Kpi({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="mb-card">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-3 mb-2">
        {icon}{label}
      </div>
      <div className="mb-display text-3xl">{value}</div>
      {sub && <div className="text-xs text-ink-3 mt-1 truncate">{sub}</div>}
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}
