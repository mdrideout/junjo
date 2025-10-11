Junjo Server Deployment
=======================

Junjo Server can be deployed in various ways depending on your needs. Being based on docker containers, it's easy to deploy Junjo Server anywhere with docker compose.

Digital Ocean VM Deployment Example
------------------------------------

For a complete production junjo server deployment example to a fresh virtual machine using Docker Compose, Caddy reverse proxy, and automatic HTTPS, see the `Junjo Server Deployment Example <https://github.com/mdrideout/junjo-server-deployment-example>`_.

This example demonstrates:

- **Low-cost VM setup** - Runs on a 1GB RAM VM with all services
- **Microservices architecture** - Separate containers for:

  - Junjo Server Ingestion (gRPC telemetry endpoint)
  - Junjo Server Backend (API & authentication)
  - Junjo Server Frontend (Web UI)

- **Automatic HTTPS** - Caddy reverse proxy with Let's Encrypt SSL
- **Subdomain routing** - Clean URLs for different services:

  - Web UI: ``https://junjo.example.com``
  - API: ``https://api.junjo.example.com``
  - Ingestion: ``grpc.junjo.example.com:443``

- **Data persistence** - Optional block storage for scalable data management
- **Production-ready configuration** - Environment variables, Docker networking, and service orchestration

The deployment guide walks through setting up a VM, configuring DNS, installing Docker, and launching all services with a single command.