/**
 * MobileDrawer — slide-in left navigation panel for mobile.
 *
 * Mirrors the desktop Sidebar's NAV array but always renders icon + text
 * (no hover-to-expand on touch). Adds the bits that live in the desktop
 * TopBar — UsagePill (plan + usage at a glance) and the Add-job CTA — so
 * the bar above can stay minimal. Sign-out moves down here too, matching
 * the Sidebar pattern.
 *
 * Close paths (triple lock so a future addition can't break the contract):
 *   1. Tapping any nav item — onClick on each NavLink.
 *   2. Tapping the scrim — onClick on the backdrop.
 *   3. Route change — handled by AppShell via a useLocation effect.
 */
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Briefcase, FileText, UserCircle, LogOut, Plus, X, Sparkles } from 'lucide-react';
import { UsagePill } from './UsagePill';
import { useAuth } from '@/hooks/useAuth';

const NAV = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Jobs', Icon: Briefcase, end: false },
  { to: '/cv', label: 'CV builder', Icon: FileText, end: false },
  { to: '/profile', label: 'Profile', Icon: UserCircle, end: false },
];

export function MobileDrawer({
  open,
  onClose,
  onAddJob,
}: {
  open: boolean;
  onClose: () => void;
  onAddJob: () => void;
}) {
  const { logout } = useAuth();

  return (
    <>
      {/* Scrim. pointer-events flipped with `open` so the page is fully
          interactive when the drawer is closed; we don't want a phantom
          tap-eater layer above content. */}
      <div
        onClick={onClose}
        aria-hidden
        className={`md:hidden fixed inset-0 z-40 bg-ink/50 transition-opacity duration-200 ${
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
      />

      <aside
        aria-hidden={!open}
        className={`md:hidden fixed top-0 left-0 z-50 h-full w-[280px] bg-ink text-white/85 flex flex-col transition-transform duration-200 ease-out ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-14 flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="text-rust shrink-0" />
            <span className="mb-display text-white text-base">Matchbook</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="w-9 h-9 -mr-1 flex items-center justify-center rounded-lg hover:bg-white/5"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="flex-1 px-2 space-y-1 overflow-y-auto">
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg transition relative ${
                  isActive ? 'bg-white/10 text-white' : 'hover:bg-white/5'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r bg-rust" />
                  )}
                  <Icon size={18} className="shrink-0" />
                  <span className="text-sm whitespace-nowrap">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 pt-3 pb-4 space-y-3 border-t border-white/10 shrink-0">
          {/* UsagePill renders its own Link to /billing. We wrap in a tap
              listener so picking it also collapses the drawer; the route
              change effect in AppShell would do the same a tick later but
              this avoids the visible double-frame. */}
          <div onClick={onClose} className="flex">
            <UsagePill />
          </div>

          <button
            type="button"
            onClick={() => {
              onAddJob();
              onClose();
            }}
            className="mb-btn-primary w-full"
          >
            <Plus size={16} />
            Add job
          </button>

          <button
            type="button"
            onClick={() => {
              logout();
              onClose();
            }}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 text-left text-sm"
          >
            <LogOut size={18} className="shrink-0" />
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
