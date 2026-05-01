/**
 * AppShell — the outer layout every authenticated page renders inside.
 * Owns the quick-add SlidePanel so any page can trigger it via context,
 * and the mobile-nav drawer state.
 *
 * Two layout modes split at the `md:` breakpoint (768px):
 *   - md+: fixed icon Sidebar on the left + sticky TopBar on the right.
 *   - <md: glassmorphic MobileTopBar on top + slide-in MobileDrawer.
 *
 * The drawer state lives here (not in the components) so the route-change
 * effect can close it from one place — that's the third (belt-and-braces)
 * close path in addition to nav-item taps and scrim taps.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { MobileTopBar } from './MobileTopBar';
import { MobileDrawer } from './MobileDrawer';
import { QuickAddPanel } from '@/components/QuickAddPanel';

interface AppShellCtx {
  openQuickAdd: () => void;
}

const Ctx = createContext<AppShellCtx | null>(null);

export function useAppShell() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppShell outside provider');
  return v;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [quickOpen, setQuickOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const openQuickAdd = useCallback(() => setQuickOpen(true), []);
  const location = useLocation();

  // Auto-close the drawer on any navigation. The drawer's own onClick
  // handlers already close it when an item is tapped; this is the
  // safety net for any future button that might forget to.
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <Ctx.Provider value={{ openQuickAdd }}>
      <div className="min-h-full bg-cream">
        <Sidebar />
        <MobileTopBar onOpenMenu={() => setNavOpen(true)} />
        <MobileDrawer
          open={navOpen}
          onClose={() => setNavOpen(false)}
          onAddJob={openQuickAdd}
        />
        {/* md:ml-14 leaves room for the desktop sidebar; below md the
            sidebar is hidden so content goes edge-to-edge. pt-14 below
            md offsets the fixed mobile bar so content doesn't slide
            under it; desktop's TopBar is sticky and takes flow space, no
            offset needed. */}
        <div className="md:ml-14 pt-14 md:pt-0">
          <TopBar onQuickAdd={openQuickAdd} />
          <main className="max-w-[1200px] mx-auto px-4 md:px-7 py-7">{children}</main>
        </div>
        <QuickAddPanel open={quickOpen} onClose={() => setQuickOpen(false)} />
      </div>
    </Ctx.Provider>
  );
}
