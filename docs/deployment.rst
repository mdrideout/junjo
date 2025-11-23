Junjo AI Studio Deployment
=======================

Junjo AI Studio can be deployed in various ways depending on your needs. Being based on docker containers, it's easy to deploy Junjo AI Studio anywhere with docker compose.

Minimal Build Template (Recommended Starting Point)
-------------------------------------------------

For a minimal, flexible Docker Compose setup that you can customize for your specific infrastructure needs, use the `Junjo AI Studio Minimal Build Template <https://github.com/mdrideout/junjo-ai-studio-minimal-build>`_.

This GitHub template repository provides:

- **Minimal configuration** - Just the three core services (frontend, backend, ingestion)
- **Maximum flexibility** - Bring your own reverse proxy, SSL/TLS, and networking
- **Multiple deployment scenarios** - Local development, cloud platforms, or custom infrastructure
- **Clean starting point** - No opinionated configurations to remove

**Perfect for:**

- Teams with existing infrastructure
- Custom deployment requirements
- Local development environments
- Learning Junjo AI Studio architecture
- Integration into existing docker-compose.yml files

**Quick start:**

.. code-block:: bash

    # Use as GitHub template or clone
    git clone https://github.com/mdrideout/junjo-ai-studio-minimal-build.git
    cd junjo-ai-studio-minimal-build

    # Configure environment
    cp .env.example .env
    # Edit .env with your settings

    # Start services
    docker compose up -d

    # Access UI
    open http://localhost:5153

Digital Ocean VM Deployment Example
------------------------------------

For a complete production Junjo AI Studio deployment example to a fresh virtual machine using Docker Compose, Caddy reverse proxy, and automatic HTTPS, see the `Junjo AI Studio Deployment Example <https://github.com/mdrideout/junjo-ai-studio-deployment-example>`_.

This example demonstrates:

- **Low-cost VM setup** - Runs on a 1GB RAM VM with all services
- **Microservices architecture** - Separate containers for:

  - Junjo AI Studio Ingestion (gRPC opentelemetry endpoint)
  - Junjo AI Studio Backend (API & authentication)
  - Junjo AI Studio Frontend (Web UI)

- **Automatic HTTPS** - Caddy reverse proxy with Let's Encrypt SSL
- **Subdomain routing** - Clean URLs for different services:

  - Web UI: ``https://junjo.example.com``
  - API: ``https://api.junjo.example.com``
  - Ingestion: ``grpc.junjo.example.com:443``

- **Data persistence** - Optional block storage for scalable data management
- **Production-ready configuration** - Environment variables, Docker networking, and service orchestration

The deployment guide walks through setting up a VM, configuring DNS, installing Docker, and launching all services with a single command.