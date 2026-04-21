/**
 * Icon-only sidebar that expands to 220px on hover (handoff §7.3).
 * Dark ink background, white icon tints, rust accent on the active
 * nav item (via a leading dot).
 */
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Briefcase, FileText, UserCircle, LogOut, Sparkles } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

const NAV = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Jobs', Icon: Briefcase, end: false },
  // CV builder sits between Jobs and Profile so the candidate-output
  // features (jobs + CV) cluster together at the top of the nav.
  { to: '/cv', label: 'CV builder', Icon: FileText, end: false },
  { to: '/profile', label: 'Profile', Icon: UserCircle, end: false },
];

export function Sidebar() {
  const { logout } = useAuth();
  return (
    <aside className="group fixed left-0 top-0 h-full bg-ink text-white/85 w-14 hover:w-[220px] transition-all z-30 flex flex-col overflow-hidden">
      <div className="h-14 flex items-center gap-2 px-4 shrink-0">
        <Sparkles size={20} className="text-rust shrink-0" />
        <span className="mb-display text-white opacity-0 group-hover:opacity-100 transition">
          Matchbook
        </span>
      </div>

      <nav className="flex-1 px-2 space-y-1">
        {NAV.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg transition relative ${
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
                <span className="text-sm opacity-0 group-hover:opacity-100 transition whitespace-nowrap">
                  {label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={logout}
        className="mx-2 mb-3 flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 text-left"
      >
        <LogOut size={18} className="shrink-0" />
        <span className="text-sm opacity-0 group-hover:opacity-100 transition whitespace-nowrap">
          Sign out
        </span>
      </button>
    </aside>
  );
}
