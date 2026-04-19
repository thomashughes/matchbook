/**
 * ProfilePage — read + edit the fields Claude generated at onboarding.
 *
 * Only the fields we actually use in scoring are editable here: seniority,
 * skills, salary band, remote preference, notice, career goals. The
 * full Claude-generated object remains in structured_data for provenance
 * and is shown read-only at the bottom for transparency.
 */
import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import { useProfile } from '@/api/hooks';
import { useQueryClient } from '@tanstack/react-query';
import type { Profile } from '@/types/models';

export function ProfilePage() {
  const prof = useProfile();
  const qc = useQueryClient();
  const [form, setForm] = useState<Partial<Profile>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (prof.data) setForm(prof.data);
  }, [prof.data]);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await api<Profile>('/profile', { method: 'PATCH', body: form });
      await qc.invalidateQueries({ queryKey: ['profile'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } finally {
      setSaving(false);
    }
  }

  if (prof.isLoading) return <div className="text-ink-3">Loading…</div>;
  if (!prof.data) return <div className="text-ink-3">No profile yet.</div>;

  return (
    <div className="space-y-5 max-w-2xl">
      <h1 className="mb-display text-2xl">Your profile</h1>

      <div className="mb-card space-y-4">
        <Field label="Seniority">
          <input
            className="mb-input"
            value={form.seniority_level ?? ''}
            onChange={(e) => setForm({ ...form, seniority_level: e.target.value })}
            placeholder="e.g. mid, senior, staff"
          />
        </Field>

        <Field label="Hard skills (comma separated)">
          <input
            className="mb-input"
            value={(form.hard_skills ?? []).join(', ')}
            onChange={(e) => setForm({ ...form, hard_skills: splitList(e.target.value) })}
          />
        </Field>

        <Field label="Soft skills (comma separated)">
          <input
            className="mb-input"
            value={(form.soft_skills ?? []).join(', ')}
            onChange={(e) => setForm({ ...form, soft_skills: splitList(e.target.value) })}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Minimum salary (£)">
            <input
              type="number"
              className="mb-input"
              value={form.salary_min ?? ''}
              onChange={(e) => setForm({ ...form, salary_min: e.target.value ? Number(e.target.value) : null })}
            />
          </Field>
          <Field label="Ideal salary (£)">
            <input
              type="number"
              className="mb-input"
              value={form.salary_ideal ?? ''}
              onChange={(e) => setForm({ ...form, salary_ideal: e.target.value ? Number(e.target.value) : null })}
            />
          </Field>
        </div>

        <Field label="Remote preference">
          <select
            className="mb-input"
            value={form.remote_preference ?? ''}
            onChange={(e) => setForm({ ...form, remote_preference: e.target.value || null })}
          >
            <option value="">—</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </select>
        </Field>

        <Field label="Notice period">
          <input
            className="mb-input"
            value={form.notice_period ?? ''}
            onChange={(e) => setForm({ ...form, notice_period: e.target.value || null })}
          />
        </Field>

        <Field label="Career goals">
          <textarea
            className="mb-input min-h-[100px]"
            value={form.career_goals ?? ''}
            onChange={(e) => setForm({ ...form, career_goals: e.target.value || null })}
          />
        </Field>

        <div className="flex items-center justify-end gap-3">
          {saved && <span className="text-sm text-teal">Saved</span>}
          <button className="mb-btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-label mb-1">{label}</div>
      {children}
    </label>
  );
}

function splitList(s: string): string[] {
  return s.split(',').map((x) => x.trim()).filter(Boolean);
}
