/**
 * CollapsibleSection — shared `mb-card` shell with a clickable header
 * that toggles a body. Used by the six AI panels on JobDetailPage so
 * the page fits on one screen by default.
 *
 * State is local only — re-mounting (e.g. navigating between jobs)
 * resets all panels to closed. That's intentional per the design spec.
 */
import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export function CollapsibleSection({
  title,
  hint,
  defaultOpen = false,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-card">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 text-left"
      >
        <ChevronDown
          size={16}
          className={`text-ink-3 transition-transform ${open ? '' : '-rotate-90'}`}
        />
        <span className="mb-display text-lg flex-1">{title}</span>
        {hint !== undefined && hint !== null && (
          <span className="text-xs text-ink-3">{hint}</span>
        )}
      </button>
      {open && <div className="mt-4">{children}</div>}
    </div>
  );
}
