/**
 * JobsPage — full list of tracked jobs with server-side search.
 *
 * The search box debounces locally then passes the query to /jobs,
 * which runs an ILIKE over title/company. Empty result states differ:
 * "no jobs yet" (first-time) vs "no matches" (active search).
 */
import { useEffect, useState } from 'react';
import { Search, Plus, Briefcase } from 'lucide-react';
import { useJobs } from '@/api/hooks';
import { JobCard } from '@/components/ui/JobCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { useAppShell } from '@/components/layout/AppShell';

export function JobsPage() {
  const [raw, setRaw] = useState('');
  const [q, setQ] = useState('');
  const { openQuickAdd } = useAppShell();

  useEffect(() => {
    const t = setTimeout(() => setQ(raw.trim()), 250);
    return () => clearTimeout(t);
  }, [raw]);

  const jobs = useJobs(q || undefined);
  const list = jobs.data ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="mb-display text-2xl">Your jobs</h1>
        <button className="mb-btn-primary" onClick={openQuickAdd}>
          <Plus size={16} /> Add job
        </button>
      </div>

      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder="Search by title or company…"
          className="mb-input pl-9"
        />
      </div>

      {list.length === 0 ? (
        q ? (
          <EmptyState
            icon={Search}
            title="No matches"
            subtitle={`Nothing in your list matches "${q}".`}
          />
        ) : (
          <EmptyState
            icon={Briefcase}
            title="No jobs yet"
            subtitle="Paste your first job description to see how well it fits."
            cta={<button className="mb-btn-primary" onClick={openQuickAdd}><Plus size={16} /> Add a job</button>}
          />
        )
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {list.map((j) => <JobCard key={j.id} job={j} />)}
        </div>
      )}
    </div>
  );
}
