# ── Stage 1: build the Vite SPA ──────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# VITE_API_URL is injected at build time so the JS bundle knows where the API is.
# Override this via docker compose environment or --build-arg when building.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 2: serve the static bundle with nginx ───────────────────────────────
FROM nginx:alpine

# Copy built SPA into nginx's default serve directory
COPY --from=builder /app/dist /usr/share/nginx/html

# SPA routing: unknown paths fall back to index.html instead of 404
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]