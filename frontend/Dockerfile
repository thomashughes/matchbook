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
# nginxinc/nginx-unprivileged is the official nginx image rebuilt to run
# as uid 101 (nginx) end-to-end. The stock nginx:alpine image starts the
# master as root so it can bind :80 and only drops the workers — an RCE
# in the master would still be root inside the container. The unprivileged
# variant binds :8080 instead (no root required) and worker + master both
# run as nginx. Compose maps host :3085 → container :8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine

# COPY into /etc/nginx and /usr/share/nginx requires write perms; the base
# image runs as `nginx` by default, so flip to root for the copies and
# return to nginx before the entrypoint takes over.
USER root
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.inc /etc/nginx/conf.d/security-headers.inc
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx

# Unprivileged nginx cannot bind a port <1024 without CAP_NET_BIND_SERVICE.
# 8080 is the conventional unprivileged HTTP port.
EXPOSE 8080
