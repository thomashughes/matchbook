/**
 * MobileTopBar — fixed glassmorphic bar shown below the md breakpoint.
 *
 * Sits in the top-bar role only on small screens; the desktop `Sidebar` +
 * `TopBar` pair are hidden by media query at the same breakpoint, so this
 * doesn't double up. Visually paired with `MobileDrawer`, which the
 * hamburger button opens.
 *
 * Glass effect = blur + saturate over a translucent cream tint. We use
 * inline style rather than a token utility because it's a one-off here and
 * the WebKit-prefixed property doesn't compose cleanly via Tailwind.
 */
import { Menu, Sparkles } from 'lucide-react';
import { useAuthStore } from '@/stores/auth';

export function MobileTopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const user = useAuthStore((s) => s.user);
  const initial = user?.email?.[0]?.toUpperCase() ?? '?';

  return (
    <header
      className="md:hidden fixed top-0 inset-x-0 z-30 h-14 flex items-center justify-between px-4"
      style={{
        // Translucent cream so the page colour bleeds through the blur.
        // 0.6 alpha is the sweet spot — enough to read the bar as solid,
        // little enough that scrolling content shows through.
        background: 'rgba(247, 243, 238, 0.6)',
        borderBottom: '0.5px solid rgba(224, 217, 207, 0.7)',
        WebkitBackdropFilter: 'blur(16px) saturate(140%)',
        backdropFilter: 'blur(16px) saturate(140%)',
      }}
    >
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open menu"
        className="w-10 h-10 -ml-2 flex items-center justify-center rounded-lg active:bg-black/5 transition"
      >
        <Menu size={22} className="text-ink" />
      </button>

      <div className="flex items-center gap-1.5">
        <Sparkles size={16} className="text-rust" />
        <span className="mb-display text-ink text-base">Matchbook</span>
      </div>

      <div
        className="w-9 h-9 rounded-full bg-parchment text-ink flex items-center justify-center font-medium text-sm"
        title={user?.email ?? ''}
      >
        {initial}
      </div>
    </header>
  );
}
