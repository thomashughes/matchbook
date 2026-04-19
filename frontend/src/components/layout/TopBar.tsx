/**
 * TopBar — wordmark on the left, actions on the right.
 * Quick-add job button is the primary action — matches §3.7 dashboard spec.
 */
import { Plus } from 'lucide-react';
import { useAuthStore } from '@/stores/auth';

export function TopBar({ onQuickAdd }: { onQuickAdd: () => void }) {
  const user = useAuthStore((s) => s.user);
  const initial = user?.email?.[0]?.toUpperCase() ?? '?';

  return (
    <header
      className="sticky top-0 z-20 bg-cream/90 backdrop-blur flex items-center justify-between px-7 h-14"
      style={{ borderBottom: '0.5px solid var(--border)' }}
    >
      <div />
      <div className="flex items-center gap-3">
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
