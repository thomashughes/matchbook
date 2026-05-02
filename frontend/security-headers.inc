# Security headers shared across every location block.
#
# Why an include file: nginx's `add_header` does NOT inherit from outer
# scopes once any inner location uses its own `add_header`. So every
# location that emits Cache-Control / ETag also has to repeat these.
# Centralising them here keeps them consistent.
#
# Each `always` so they emit on 4xx/5xx responses too — error pages are
# a common XSS / clickjack vector if they ship without these.

add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), interest-cohort=(), payment=()" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https:; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" always;
