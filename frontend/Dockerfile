# syntax=docker/dockerfile:1

# ---- deps stage -----------------------------------------------------------
# Isolated so the build stage's `COPY . .` (source changes constantly)
# doesn't invalidate this layer's cache on every rebuild.
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build stage -----------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* variables are compile-time constants in Next.js -- inlined
# by webpack wherever they're referenced, client or server code alike, not
# read from the process environment at runtime. Confirmed by direct
# inspection, not assumed: building this image without this ARG and
# grepping the output showed the *default* fallback ("localhost:8000")
# baked verbatim into .next/standalone/server.js, required-server-files.json,
# and routes-manifest.json. So this has to be a build ARG (supplied via
# docker build --build-arg or compose's `build.args`, see
# docker-compose.prod.yml) -- setting it under a container's runtime
# `environment:` instead (as this file originally did) would silently have
# no effect at all, and the frontend container would keep trying to reach
# a backend at localhost:8000, which doesn't exist inside its own network
# namespace once this runs as a separate container.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ---- runtime stage -----------------------------------------------------------
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --gid 1000 app \
    && adduser --uid 1000 --ingroup app --disabled-password --gecos "" app

# output: "standalone" (next.config.js) traces and copies in only the
# node_modules each page actually needs, already pruned -- no separate
# `npm install`/full node_modules tree in this stage.
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
# No public/ directory exists in this project today. If one is added later,
# it needs its own copy here too:
#   COPY --from=builder --chown=app:app /app/public ./public

USER app

EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

# NEXT_PUBLIC_API_URL is already baked into this build (see the builder
# stage's ARG/ENV above) -- there is deliberately no `environment:`/`docker
# run -e` override point for it here. Setting it at container-run time
# would silently do nothing (see the builder stage comment for how this was
# actually verified); to point this image at a different backend, rebuild
# it with a different --build-arg / compose `build.args`.
CMD ["node", "server.js"]
