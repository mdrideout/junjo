Docker Reference
================

Junjo AI Studio is distributed as three Docker images that work together to provide a complete observability platform for AI workflows. This page provides detailed reference information for deploying and configuring these services.

**Quick Start:** For a ready-to-use setup, see the `Junjo AI Studio Minimal Build Template <https://github.com/mdrideout/junjo-ai-studio-minimal-build>`_. For a complete production example with reverse proxy and HTTPS, see the `Junjo AI Studio Deployment Example <https://github.com/mdrideout/junjo-ai-studio-deployment-example>`_. More details in :doc:`deployment`.

Docker Images
-------------

Backend Service
~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-ai-studio-backend <https://hub.docker.com/r/mdrideout/junjo-ai-studio-backend>`_

The backend service provides the HTTP API, authentication, and query capabilities.

**Storage and query model (current):**

- **SQLite** for users / sessions / API keys
- **SQLite metadata index** for fast lookup of which Parquet files may contain a trace/service
- **Parquet** files for span storage (cold tier)
- **DataFusion** to query Parquet (cold + hot snapshot) and deduplicate results

**Notes:**

- Indexes new Parquet files asynchronously (polls the shared Parquet directory)
- Calls ingestion internal gRPC (``:50052``) per query to generate a hot snapshot and return a bounded list of recently-flushed cold Parquet paths (bridges flush→index lag)

Ingestion Service
~~~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-ai-studio-ingestion <https://hub.docker.com/r/mdrideout/junjo-ai-studio-ingestion>`_

The ingestion service provides high-throughput OpenTelemetry data reception using a segmented Arrow IPC write-ahead log (WAL) that flushes to date-partitioned Parquet files (constant memory flush).

**Ports:**

- ``50051`` - OpenTelemetry gRPC ingestion endpoint (public, your applications connect here)
- ``50052`` - Internal gRPC for backend queries (PrepareHotSnapshot / FlushWAL) (internal)

**Notes:**

- This is the primary endpoint where your Junjo workflows send telemetry
- Uses segmented Arrow IPC WAL for durability and throughput
- Flushes WAL → Parquet and maintains a bounded list of recently flushed Parquet paths for query bridging
- Validates API keys by calling the backend's internal auth gRPC (``:50053``)

Frontend Service
~~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-ai-studio-frontend <https://hub.docker.com/r/mdrideout/junjo-ai-studio-frontend>`_

The frontend service provides the interactive web UI for visualizing and debugging AI workflows.

**Ports:**

- ``80`` - Web UI HTTP server (public)

**Notes:**

- Static web application that communicates with the backend API
- Requires backend service to be running and healthy
- Serves interactive graph visualizations and state debugging tools

Complete Docker Compose Configuration
--------------------------------------

Minimal Build Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the standard configuration for running Junjo AI Studio, suitable for both local development and as a starting point for production.

.. code-block:: yaml
    :caption: docker-compose.yml

    # Junjo AI Studio - Minimal Build
    # A lightweight, self-hostable AI workflow debugging platform.
    # https://github.com/mdrideout/junjo-ai-studio-minimal-build

    services:
      junjo-ai-studio-backend:
        image: mdrideout/junjo-ai-studio-backend:latest
        container_name: junjo-ai-studio-backend
        restart: unless-stopped
        volumes:
          # Database storage (required for all modes)
          - ${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
        ports:
          - "1323:1323" # HTTP API (public)
        networks:
          - junjo-network
        env_file:
          - .env
        environment:
          # Override host/port for Docker network communication
          - INGESTION_HOST=junjo-ai-studio-ingestion
          - INGESTION_PORT=50052
          # Enable migrations on startup
          - RUN_MIGRATIONS=true
          # Database paths (hardcoded for Docker, users configure host mount via JUNJO_HOST_DB_DATA_PATH)
          - JUNJO_SQLITE_PATH=/app/.dbdata/sqlite/junjo.db
          - JUNJO_METADATA_DB_PATH=/app/.dbdata/sqlite/metadata.db
          - JUNJO_PARQUET_STORAGE_PATH=/app/.dbdata/spans/parquet

      junjo-ai-studio-ingestion:
        image: mdrideout/junjo-ai-studio-ingestion:latest
        container_name: junjo-ai-studio-ingestion
        restart: unless-stopped
        volumes:
          # Database storage (required for all modes)
          - ${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
        ports:
          - "50051:50051" # Public OTLP endpoint (authenticated via API key)
        networks:
          - junjo-network
        env_file:
          - .env
        environment:
          - BACKEND_GRPC_HOST=junjo-ai-studio-backend
          - BACKEND_GRPC_PORT=50053
          # Arrow IPC WAL directory
          - WAL_DIR=/app/.dbdata/spans/wal
          # Hot snapshot path (backend reads this file directly)
          - SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
          # Parquet output directory (backend indexer watches this)
          - PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
        depends_on:
          junjo-ai-studio-backend:
            condition: service_started
        healthcheck:
          test: ["CMD", "grpc_health_probe", "-addr=localhost:50052"]
          interval: 5s
          timeout: 3s
          retries: 5
          start_period: 5s

      junjo-ai-studio-frontend:
        image: mdrideout/junjo-ai-studio-frontend:latest
        container_name: junjo-ai-studio-frontend
        restart: unless-stopped
        ports:
          - "5153:80" # Public frontend (production build - nginx serving static files on port 80)
        env_file:
          - .env
        networks:
          - junjo-network
        depends_on:
          junjo-ai-studio-backend:
            condition: service_started

    networks:
      junjo-network:
        name: junjo_network
        driver: bridge

Production Deployment
---------------------

For a complete production setup on a Virtual Machine (VM) including:

*   **Caddy Reverse Proxy** for automatic HTTPS
*   **Subdomain routing** (e.g., ``junjo.example.com``)
*   **Block storage** configuration

Please refer to the `Junjo AI Studio Deployment Example <https://github.com/mdrideout/junjo-ai-studio-deployment-example>`_ repository.

Environment Variables Reference
--------------------------------

This section details the environment variables used to configure Junjo AI Studio. These are typically defined in a ``.env`` file.

Common Configuration
~~~~~~~~~~~~~~~~~~~~

``JUNJO_ENV``
    **Required.** Environment mode.

    - ``development`` (default): Uses localhost and standard ports.
    - ``production``: Expects production hostname and subdomains.

``JUNJO_ALLOW_ORIGINS``
    **Optional.** Comma-separated list of allowed CORS origins for API requests.

    - **Development Default:** ``http://localhost:5151,http://localhost:5153``
    - **Production:** Auto-derived from ``JUNJO_PROD_FRONTEND_URL`` if not set.

Security (Backend)
~~~~~~~~~~~~~~~~~~

These keys secure session cookies and must be Base64-encoded strings.

``JUNJO_SESSION_SECRET``
    **Required.** Signing key for session integrity (prevents tampering).

    - **Generate:** ``openssl rand -base64 32``

``JUNJO_SECURE_COOKIE_KEY``
    **Required.** Encryption key for session confidentiality (prevents reading).

    - **Generate:** ``openssl rand -base64 32``

Database Storage
~~~~~~~~~~~~~~~~

``JUNJO_HOST_DB_DATA_PATH``
    **Required.** Path on the host machine where database files are stored.

    - **Development Default:** ``./.dbdata`` (local directory)
    - **Production:** Use a mounted block storage path (e.g., ``/mnt/junjo-data``).

Logging
~~~~~~~

``JUNJO_LOG_LEVEL``
    Minimum severity level for logs.

    - Values: ``debug``, ``info`` (default), ``warn``, ``error``.

``JUNJO_LOG_FORMAT``
    Output format for logs.

    - ``json`` (default): Machine-readable, recommended for production.
    - ``text``: Human-readable, colored output for development.

Production URLs (Required for Production)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``JUNJO_ENV=production``, these variables configure public access points.

``JUNJO_PROD_FRONTEND_URL``
    The public URL where users access the web UI (e.g., ``https://app.example.com``).

``JUNJO_PROD_BACKEND_URL``
    The public URL for the backend API (e.g., ``https://api.example.com``). Must share the same root domain as the frontend.

``JUNJO_PROD_INGESTION_URL``
    The public URL for the ingestion service (e.g., ``https://ingestion.example.com``).

AI Service Keys (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~

API keys for LLM features in the prompt playground.

- ``GEMINI_API_KEY``
- ``OPENAI_API_KEY``
- ``ANTHROPIC_API_KEY``

Volume Mounts
-------------

All three services require persistent storage for their databases. The recommended approach is to use either local directories or block storage volumes.

Local Directory Structure
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

    .
    ├── docker-compose.yml
    ├── .env
    └── .dbdata/
        ├── sqlite/                # Backend SQLite (junjo.db + metadata.db)
        └── spans/
            ├── wal/               # Arrow IPC WAL segments (hot)
            ├── parquet/           # Date-partitioned Parquet files (cold)
            └── hot_snapshot.parquet

**Create directories:**

.. code-block:: bash

    mkdir -p .dbdata/sqlite .dbdata/spans/wal .dbdata/spans/parquet
    chmod -R 755 .dbdata

Block Storage (Production)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For production deployments, mount block storage at a consistent location:

.. code-block:: bash

    # Example: Mount block storage
    sudo mkfs.ext4 /dev/disk/by-id/scsi-0DO_Volume_junjo-data
    sudo mkdir -p /mnt/junjo-data
    sudo mount -o defaults,nofail /dev/disk/by-id/scsi-0DO_Volume_junjo-data /mnt/junjo-data

    # Create database directories
    sudo mkdir -p /mnt/junjo-data/sqlite /mnt/junjo-data/spans/wal /mnt/junjo-data/spans/parquet
    sudo chown -R $USER:$USER /mnt/junjo-data

Update volume paths in docker-compose.yml:

.. code-block:: yaml

    volumes:
      - /mnt/junjo-data:/app/.dbdata

Port Mappings
-------------

Internal Communication
~~~~~~~~~~~~~~~~~~~~~~

Services communicate internally via the Docker network. These ports do not need to be exposed to the host:

.. code-block:: text

    Backend (1323) ←→ Frontend
    Backend (50052) ←→ Ingestion (internal RPC)
    Backend (50053) ←→ Ingestion (internal auth RPC)

External Access
~~~~~~~~~~~~~~~

These ports need to be accessible:

**Development:**

- Frontend: ``http://localhost:5153`` (Web UI)
- Backend API: ``http://localhost:1323`` (Optional, usually only accessed by frontend)
- Ingestion: ``localhost:50051`` (Your applications connect here)

**Production (with reverse proxy):**

- Frontend: ``https://junjo.example.com`` (Web UI)
- Backend API: ``https://api.junjo.example.com`` (API)
- Ingestion: ``ingestion.junjo.example.com`` (gRPC with TLS - see Caddyfile routing example)

See :doc:`deployment` for production deployment examples with Caddy reverse proxy.

Resource Requirements
---------------------

Junjo AI Studio is designed to run on minimal resources:

**Minimum Recommended Resources:**

- **CPU:** 1 shared vCPU
- **RAM:** 1 GB
- **Storage:** 10 GB (more for long-term trace retention)

Network Configuration
---------------------

Docker Network
~~~~~~~~~~~~~~

All services should run on the same Docker network for internal communication:

.. code-block:: yaml

    networks:
      junjo-network:
        name: junjo_network
        driver: bridge

Production Deployment
---------------------

Reverse Proxy Setup
~~~~~~~~~~~~~~~~~~~

For production, use a reverse proxy like Caddy or Nginx to provide:

- Automatic HTTPS with Let's Encrypt
- Subdomain routing
- Load balancing (if scaling horizontally)

Example Caddyfile:

.. code-block:: text
    :caption: Caddyfile

    # Junjo AI Studio routing block
    junjo.example.com, *.junjo.example.com {
      tls your.email@gmail.com {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN} # Created inside CloudFlare and set in the .env file
        resolvers 1.1.1.1 # Cloudflare DNS is recommended for this plugin	
      }

      # backend: api.junjo.example.com
      @api host api.junjo.example.com
      handle @api {
        reverse_proxy junjo-ai-studio-backend:1323
      }

      # ingestion: ingestion.junjo.example.com
      @ingestion host ingestion.junjo.example.com
      handle @ingestion {
        reverse_proxy h2c://junjo-ai-studio-ingestion:50051
      }

      # frontend: Fallback for the root domain
      handle {
        reverse_proxy junjo-ai-studio-frontend:80
      }
    }

See the `Junjo AI Studio Deployment Example <https://github.com/mdrideout/junjo-ai-studio-deployment-example>`_ for a complete production setup.

Scaling Considerations
----------------------

Vertical Scaling
~~~~~~~~~~~~~~~~

For most deployments, vertical scaling is sufficient:

- Increase CPU/RAM allocation
- Use faster disk (NVMe SSDs)
- Increase Docker memory limits
- Split frontend, backend, and ingestion services to separate virtual machines, scaling each's resources as necessary.

Troubleshooting
---------------

Service Won't Start
~~~~~~~~~~~~~~~~~~~

Check logs for specific errors:

.. code-block:: bash

    docker compose logs junjo-ai-studio-backend
    docker compose logs junjo-ai-studio-ingestion
    docker compose logs junjo-ai-studio-frontend

Common issues:

- Missing environment variables in ``.env``
- Port conflicts (check with ``netstat -tlnp``)
- Permission issues with volume mounts
- Network not created (``docker network create junjo-network``)

API Errors
~~~~~~~~~~

If the web UI shows API errors:

- Check CORS settings in backend (``JUNJO_ALLOW_ORIGINS``)
- Verify frontend can reach backend API
- Check backend logs for specific errors
- Verify session secret is set in production

Next Steps
----------

- See :doc:`junjo_ai_studio` for setup and configuration
- Review :doc:`deployment` for production deployment examples
- Explore :doc:`opentelemetry` for application instrumentation
