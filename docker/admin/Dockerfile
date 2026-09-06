# DuckClaw Admin (Next.js standalone)
# Build: docker build -f docker/admin/Dockerfile -t duckclaw/admin:latest .

FROM node:20-bookworm AS deps
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
COPY apps/duckclaw-admin/package.json apps/duckclaw-admin/pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile

FROM node:20-bookworm AS builder
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
# Preserve monorepo-relative import:
# apps/duckclaw-admin → ../../../../packages/shared/...
COPY --from=deps /app/node_modules /build/apps/duckclaw-admin/node_modules
COPY packages/shared/src/duckclaw/seeds /build/packages/shared/src/duckclaw/seeds
COPY apps/duckclaw-admin/ /build/apps/duckclaw-admin/
WORKDIR /build/apps/duckclaw-admin
ENV NEXT_TELEMETRY_DISABLED=1 \
    DUCKCLAW_ADMIN_RELAX_BUILD=1 \
    ENV=production
RUN pnpm build

FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3001 \
    HOSTNAME=0.0.0.0

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin duckclaw

COPY --from=builder /build/apps/duckclaw-admin/public ./public
COPY --from=builder --chown=duckclaw:duckclaw /build/apps/duckclaw-admin/.next/standalone ./
COPY --from=builder --chown=duckclaw:duckclaw /build/apps/duckclaw-admin/.next/static ./.next/static

USER duckclaw
EXPOSE 3001
# Next standalone may nest under apps/duckclaw-admin when built from monorepo layout
CMD ["sh", "-c", "if [ -f server.js ]; then node server.js; else node apps/duckclaw-admin/server.js; fi"]
