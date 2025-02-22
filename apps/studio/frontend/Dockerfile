FROM node:22-bookworm-slim

# Set the working directory inside the container
WORKDIR /app

# Copy package.json and yarn.lock (or package-lock.json if using npm)
COPY package*.json ./

# Install dependencies to the new volume location
RUN npm install --prefix ./

# Copy the rest of the frontend code
COPY . .

# Environment variables for Vite HMR with Docker (important!)
ENV CHOKIDAR_USEPOLLING=true
ENV WDS_SOCKET_HOST=0.0.0.0
ENV WDS_SOCKET_PORT=4951

# Expose the hmr port Vite uses (4951)
EXPOSE 4951

# Start the Vite development server with hot reloading
CMD ["npm", "run", "dev"] 