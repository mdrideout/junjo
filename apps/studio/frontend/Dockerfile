# ---- Base Stage ----
# Installs dependencies, creating a cached layer.
FROM node:22-bookworm-slim as base
WORKDIR /app
COPY package*.json ./
RUN npm install --prefix ./

# ---- Builder Stage ----
# Builds the production-ready static assets.
FROM base as builder
COPY . .
RUN npm run build

# ---- Production Stage ----
# The final, lightweight production image.
FROM nginx:stable-alpine as production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Copy the startup script and make it executable
COPY prod-startup.sh /docker-entrypoint.d/40-startup-message.sh
RUN chmod +x /docker-entrypoint.d/40-startup-message.sh
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# ---- Development Stage ----
# Runs the Vite dev server with hot-reloading.
FROM base as development
WORKDIR /app
COPY . .
# Environment variables for Vite HMR with Docker
ENV CHOKIDAR_USEPOLLING=true
ENV WDS_SOCKET_HOST=0.0.0.0
ENV WDS_SOCKET_PORT=4951
EXPOSE 4951
CMD ["npm", "run", "dev"]