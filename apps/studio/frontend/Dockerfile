# ---- Base Stage ----
# Installs dependencies, creating a cached layer.
FROM node:22-bookworm-slim AS base
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

# ---- Builder Stage ----
# Builds the production-ready static assets.
FROM base AS builder
COPY frontend/ .
RUN npm run build

# ---- Production Stage ----
# The final, lightweight production image.
FROM nginx:stable-alpine AS production
LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/junjo-ai-studio/
COPY licenses/frontend-production.json /usr/share/licenses/junjo-ai-studio/
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
# Copy the startup script and make it executable
COPY frontend/prod-startup.sh /docker-entrypoint.d/40-startup-message.sh
RUN chmod +x /docker-entrypoint.d/40-startup-message.sh
EXPOSE 26153
CMD ["nginx", "-g", "daemon off;"]

# ---- Development Stage ----
# Runs the Vite dev server with hot-reloading.
FROM base AS development
WORKDIR /app
COPY frontend/ .
ENV CHOKIDAR_USEPOLLING=true
EXPOSE 26151
CMD ["npm", "run", "dev"]
