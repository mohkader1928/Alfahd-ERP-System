# NEXT_PUBLIC_* vars are baked into the client bundle at build time, not
# read at runtime — must be passed as build args, not just env vars on the
# running container.
FROM node:22-slim AS builder
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Standalone output already traces and copies only the node_modules actually
# used at runtime — no separate prod-install step needed here.
FROM node:22-slim AS production
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
