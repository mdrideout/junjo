# ---- Base Stage ----
# Installs dependencies, creating a cached layer.
FROM node:22-bookworm-slim AS base
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --prefix ./

# ---- Builder Stage ----
# Builds the production-ready static assets.
FROM base AS builder

COPY frontend/package*.json ./
RUN npm install --prefix ./

COPY frontend/ .
RUN npm run build

# ---- Production Stage ----
# The final, lightweight production image.
FROM nginx:stable-alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
# Copy the startup script and make it executable
COPY frontend/prod-startup.sh /docker-entrypoint.d/40-startup-message.sh
RUN chmod +x /docker-entrypoint.d/40-startup-message.sh
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# ---- Development Stage ----
# Runs the Vite dev server with hot-reloading.
FROM base AS development
WORKDIR /app
COPY frontend/ .
ENV CHOKIDAR_USEPOLLING=true
EXPOSE 5151
CMD ["npm", "run", "dev"]
