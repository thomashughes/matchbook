/**
 * DonePage — onboarding complete. Celebrate and route into the app.
 */
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

export function DonePage() {
  return (
    <div className="min-h-full bg-cream flex items-center justify-center p-6">
      <div className="mb-card w-full max-w-xl text-center">
        <div className="inline-flex w-12 h-12 rounded-full bg-teal/10 items-center justify-center mb-4">
          <Sparkles size={22} className="text-teal" />
        </div>
        <div className="mb-display text-2xl mb-2">Your profile's ready</div>
        <p className="text-sm text-ink-2 mb-6">
          Start dropping in job descriptions or URLs and we'll score each one against it.
        </p>
        <Link to="/" className="mb-btn-primary inline-block">Go to dashboard</Link>
      </div>
    </div>
  );
}
