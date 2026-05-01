// Sanitise a user- or LLM-supplied URL before rendering into an
// anchor's `href`.
//
// Why: pasting `javascript:fetch('/api/v1/auth/me').then(...)` as a job
// source URL and then clicking the rendered link would execute that
// payload in our origin, with full access to the in-memory access
// token. React auto-escapes attribute *values* but happily renders a
// literal `javascript:` href as-is. Returning `undefined` here makes
// the resulting <a> non-clickable instead.
//
// Allowed schemes: http, https, mailto. Anything else (including
// `javascript:`, `data:`, `vbscript:`, `file:`, and protocol-relative
// `//evil.example`) is rejected. Relative URLs are accepted by treating
// them as same-origin via `new URL(value, window.location.origin)`.

const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

export function safeHref(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (!SAFE_PROTOCOLS.has(parsed.protocol)) return undefined;
    return parsed.toString();
  } catch {
    // URL constructor throws on truly malformed input — drop it.
    return undefined;
  }
}
