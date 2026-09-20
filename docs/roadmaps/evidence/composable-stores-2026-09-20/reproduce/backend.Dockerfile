# Both variants reuse this production image's identical, verified backend uv.lock.
ARG BASE_IMAGE=junjo-adk-fc0e-backend:latest
FROM ${BASE_IMAGE}
COPY app /app/app
