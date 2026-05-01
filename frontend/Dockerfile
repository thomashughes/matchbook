# Matchbook v2 frontend — build once with Node, serve as static files via Nginx.
#
# Two-stage build:
#   1. Node stage compiles TypeScript + Vite into /app/dist.
#   2. Nginx stage copies only /dist into a tiny runtime image.
# Final image has no Node, no node_modules, no source — ~30MB vs ~1GB.

# --- Stage 1: build --------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Copy manifest first so `npm ci` caches independently of source changes.
COPY package.json ./
# npm install (not ci) because we don't commit the lockfile yet — Phase 1
# is pre-lockfile. Phase 5 (CI/CD hardening) switches to `npm ci` against
# a committed package-lock.json for reproducible builds.
RUN npm install

COPY . .

# VITE_ env vars are inlined into the static bundle at build time, so
# they're passed as build args by docker-compose.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# --- Stage 2: runtime ------------------------------------------------------
FROM nginx:1.27-alpine

# Replace the default config with one tuned for a React SPA (needs the
# try_files fallback to index.html so client-side routes 200 instead of 404).
# security-headers.inc is included from nginx.conf at request time.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.inc /etc/nginx/conf.d/security-headers.inc

COPY --from=build /app/dist /usr/share/nginx/html

# Nginx listens on 80 inside the container; docker-compose maps that to 3085.
EXPOSE 80
