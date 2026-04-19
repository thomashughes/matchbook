/**
 * EmptyState — icon + headline + subhead + CTA.
 *
 * §7.4 rule: every empty state must include a clear CTA. No blank "no
 * data found" screens. We enforce the shape here so pages can't skip
 * the CTA accidentally.
 */
import type { ComponentType, ReactNode } from 'react';

interface Props {
  icon: ComponentType<{ size?: string | number; className?: string }>;
  title: string;
  subtitle?: string;
  cta?: ReactNode;
}

export function EmptyState({ icon: Icon, title, subtitle, cta }: Props) {
  return (
    <div className="mb-card flex flex-col items-center text-center py-10">
      <div className="w-12 h-12 rounded-full bg-parchment flex items-center justify-center">
        <Icon size={22} className="text-ink-2" />
      </div>
      <div className="mb-display text-xl text-ink mt-4">{title}</div>
      {subtitle && <p className="text-sm text-ink-2 mt-1 max-w-sm">{subtitle}</p>}
      {cta && <div className="mt-5">{cta}</div>}
    </div>
  );
}
