FROM node:22-bookworm-slim

LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 26251

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
