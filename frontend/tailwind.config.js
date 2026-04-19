/**
 * Warm Modern design tokens, as specified in handoff §7.
 *
 * Colours are exposed both as CSS custom properties (see globals.css) and
 * as Tailwind theme tokens here. The custom-property layer is the source
 * of truth so we can switch themes at runtime later without rebuilding.
 * Tailwind reads var(--token) so class names like `bg-card` work too.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: 'var(--cream)',
        parchment: 'var(--parchment)',
        card: 'var(--card)',
        border: 'var(--border)',
        ink: 'var(--ink)',
        'ink-2': 'var(--ink-2)',
        'ink-3': 'var(--ink-3)',
        teal: 'var(--teal)',
        'teal-light': 'var(--teal-light)',
        rust: 'var(--rust)',
        'rust-light': 'var(--rust-light)',
        gold: 'var(--gold)',
        'gold-light': 'var(--gold-light)',
      },
      fontFamily: {
        // Display uses Fraunces — opsz-variable serif with personality.
        // Body uses Geist — clean geometric sans for UI.
        display: ['"Fraunces"', 'ui-serif', 'Georgia', 'serif'],
        sans: ['"Geist"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        card: '12px',
      },
      borderWidth: {
        hairline: '0.5px',
      },
    },
  },
  plugins: [],
};
