/**
 * SlidePanel — right-side slide-in surface for quick-add job and
 * future ancillary flows. Uses inert backdrop + fixed panel rather than
 * a library to keep the bundle lean. Focus restoration on close is a
 * Phase 5 polish item.
 */
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

export function SlidePanel({ open, onClose, title, children }: Props) {
  // Lock body scroll while open — otherwise the page scrolls underneath
  // the panel, disorienting users.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <div
      className={`fixed inset-0 z-40 transition ${open ? '' : 'pointer-events-none'}`}
      aria-hidden={!open}
    >
      <div
        className={`absolute inset-0 bg-ink/30 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <aside
        className={`absolute right-0 top-0 h-full w-full max-w-md bg-cream shadow-xl transition-transform ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="flex items-center justify-between p-5" style={{ borderBottom: '0.5px solid var(--border)' }}>
          <div className="mb-display text-lg">{title}</div>
          <button onClick={onClose} className="text-ink-3 hover:text-ink" aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <div className="p-5 overflow-y-auto h-[calc(100%-57px)]">{children}</div>
      </aside>
    </div>
  );
}
