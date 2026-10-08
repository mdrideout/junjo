# ---- Base Stage ----
# Installs dependencies, creating a cached layer.
FROM node:22-bookworm-slim AS base
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

# ---- Development Stage ----
# Runs the Vite dev server with hot-reloading.
FROM base AS development
WORKDIR /app
COPY frontend/ .
ENV CHOKIDAR_USEPOLLING=true
EXPOSE 26151
CMD ["npm", "run", "dev"]
