import type { ReactNode } from 'react';

/**
 * Shared layout for every auth page.
 *
 * Centred card on a cream background with the wordmark above — provides
 * a consistent visual frame across login / register / verify / reset
 * without repeating layout code on each page. The display typeface
 * (Fraunces) is used for the wordmark so the brand voice is visible from
 * the first screen users see.
 */
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="min-h-full flex items-center justify-center bg-cream px-4 py-10">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="mb-display text-3xl text-ink">Matchbook</div>
          <p className="mt-1 text-ink-3 text-sm">The thoughtful job-search companion.</p>
        </div>

        <div className="mb-card">
          <h1 className="mb-display text-2xl text-ink mb-1">{title}</h1>
          {subtitle && <p className="text-ink-2 text-sm mb-5">{subtitle}</p>}
          {children}
        </div>

        {footer && <div className="text-center mt-5 text-sm text-ink-2">{footer}</div>}
      </div>
    </div>
  );
}
