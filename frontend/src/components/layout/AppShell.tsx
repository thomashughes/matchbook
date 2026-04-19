/**
 * AppShell — the outer layout every authenticated page renders inside.
 * Owns the quick-add SlidePanel so any page can trigger it via context.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
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
  const openQuickAdd = useCallback(() => setQuickOpen(true), []);

  return (
    <Ctx.Provider value={{ openQuickAdd }}>
      <div className="min-h-full bg-cream">
        <Sidebar />
        <div className="ml-14">
          <TopBar onQuickAdd={openQuickAdd} />
          <main className="max-w-[1200px] mx-auto px-7 py-7">{children}</main>
        </div>
        <QuickAddPanel open={quickOpen} onClose={() => setQuickOpen(false)} />
      </div>
    </Ctx.Provider>
  );
}
