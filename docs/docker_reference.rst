Docker Reference
================

Junjo Server is distributed as three Docker images that work together to provide a complete observability platform for AI workflows. This page provides detailed reference information for deploying and configuring these services.

**Quick Start:** For a ready-to-use setup, see the `Junjo Server Bare-Bones Template <https://github.com/mdrideout/junjo-server-bare-bones>`_. For a complete production example with reverse proxy and HTTPS, see the `Junjo Server Deployment Example <https://github.com/mdrideout/junjo-server-deployment-example>`_. More details in :doc:`deployment`.

Docker Images
-------------

Backend Service
~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-server-backend <https://hub.docker.com/r/mdrideout/junjo-server-backend>`_

The backend service provides the HTTP API, authentication, and data processing capabilities. It uses SQLite for metadata storage and DuckDB for analytical queries.

**Ports:**

- ``1323`` - HTTP API server (public)
- ``50053`` - Internal gRPC for service communication (internal)

**Volumes:**

- ``/dbdata/sqlite`` - SQLite database directory (persistent)
- ``/dbdata/duckdb`` - DuckDB database directory (persistent)

**Notes:**

- Requires root user or appropriate permissions for database write operations
- Polls the ingestion service for new telemetry data
- Processes and indexes traces for querying via the web UI

Ingestion Service
~~~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-server-ingestion-service <https://hub.docker.com/r/mdrideout/junjo-server-ingestion-service>`_

The ingestion service provides high-throughput OpenTelemetry data reception using BadgerDB as a write-ahead log. This decoupled architecture ensures telemetry data is never lost, even under heavy load.

**Ports:**

- ``50051`` - OpenTelemetry gRPC ingestion endpoint (public, your applications connect here)
- ``50052`` - Internal gRPC for backend polling (internal)

**Volumes:**

- ``/dbdata/badgerdb`` - BadgerDB write-ahead log directory (persistent)

**Notes:**

- This is the primary endpoint where your Junjo workflows send telemetry
- Uses BadgerDB for durable, high-performance data ingestion
- Backend service polls this service to retrieve new data

Frontend Service
~~~~~~~~~~~~~~~~

**Image:** `mdrideout/junjo-server-frontend <https://hub.docker.com/r/mdrideout/junjo-server-frontend>`_

The frontend service provides the interactive web UI for visualizing and debugging AI workflows.

**Ports:**

- ``80`` - Web UI HTTP server (public)

**Notes:**

- Static web application that communicates with the backend API
- Requires backend service to be running and healthy
- Serves interactive graph visualizations and state debugging tools

Complete Docker Compose Configuration
--------------------------------------

Production-Ready Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This configuration includes all three services with best practices for production deployment:

.. code-block:: yaml
    :caption: docker-compose.yml

    services:
      # Backend API and data processing service
      junjo-server-backend:
        image: mdrideout/junjo-server-backend:latest
        container_name: junjo-server-backend
        restart: unless-stopped
        ports:
          - "1323:1323"   # HTTP API (public)
          - "50053:50053" # Internal gRPC (backend communication)
        volumes:
          # Persistent database storage
          - ./dbdata/sqlite:/dbdata/sqlite
          - ./dbdata/duckdb:/dbdata/duckdb
        environment:
          # Environment (production|development)
          - JUNJO_ENV=${JUNJO_ENV:-production}
          # CORS origins (comma-separated)
          - JUNJO_ALLOW_ORIGINS=${JUNJO_ALLOW_ORIGINS}
          # Session secret for authentication (generate with: openssl rand -hex 32)
          - JUNJO_SESSION_SECRET=${JUNJO_SESSION_SECRET}
          # Production authentication domain
          - JUNJO_PROD_AUTH_DOMAIN=${JUNJO_PROD_AUTH_DOMAIN}
        networks:
          - junjo-network
        healthcheck:
          test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:1323/health"]
          interval: 30s
          timeout: 10s
          retries: 3
          start_period: 40s

      # OpenTelemetry data ingestion service
      junjo-server-ingestion:
        image: mdrideout/junjo-server-ingestion-service:latest
        container_name: junjo-server-ingestion
        restart: unless-stopped
        ports:
          - "50051:50051" # OTel gRPC ingestion (public, your apps connect here)
          - "50052:50052" # Internal gRPC (backend polling)
        volumes:
          # BadgerDB write-ahead log
          - ./dbdata/badgerdb:/dbdata/badgerdb
        environment:
          # API key for authentication (generate in web UI)
          - JUNJO_SERVER_API_KEY=${JUNJO_SERVER_API_KEY}
        networks:
          - junjo-network
        depends_on:
          junjo-server-backend:
            condition: service_healthy # Wait for backend server to be healthy before starting
        healthcheck:
          test: ["CMD", "grpc_health_probe", "-addr=:50051"]
          interval: 30s
          timeout: 10s
          retries: 3
          start_period: 40s

      # Web UI for visualization and debugging
      junjo-server-frontend:
        image: mdrideout/junjo-server-frontend:latest
        container_name: junjo-server-frontend
        restart: unless-stopped
        ports:
          - "5153:80" # Web UI
        environment:
          # Backend API URL (adjust for your deployment)
          - VITE_API_URL=${VITE_API_URL:-http://localhost:1323}
        networks:
          - junjo-network
        depends_on:
          junjo-server-backend:
            condition: service_healthy
          junjo-server-ingestion:
            condition: service_healthy

    networks:
      junjo-network:
        driver: bridge

Development Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

For local development, you can use a simpler configuration:

.. code-block:: yaml
    :caption: docker-compose.dev.yml

    services:
      junjo-server-backend:
        image: mdrideout/junjo-server-backend:latest
        ports:
          - "1323:1323"
          - "50053:50053"
        volumes:
          - ./.dbdata/sqlite:/dbdata/sqlite
          - ./.dbdata/duckdb:/dbdata/duckdb
        environment:
          - JUNJO_ENV=development
          - JUNJO_ALLOW_ORIGINS=http://localhost:5153
        networks:
          - junjo-network

      junjo-server-ingestion:
        image: mdrideout/junjo-server-ingestion-service:latest
        ports:
          - "50051:50051"
          - "50052:50052"
        volumes:
          - ./.dbdata/badgerdb:/dbdata/badgerdb
        networks:
          - junjo-network

      junjo-server-frontend:
        image: mdrideout/junjo-server-frontend:latest
        ports:
          - "5153:80"
        environment:
          - VITE_API_URL=http://localhost:1323
        networks:
          - junjo-network

    networks:
      junjo-network:
        driver: bridge

Environment Variables Reference
--------------------------------

Backend Service
~~~~~~~~~~~~~~~

``JUNJO_ENV``
    **Required.** Environment mode: ``production`` or ``development``

    - **Default:** None
    - **Example:** ``JUNJO_ENV=production``

``JUNJO_ALLOW_ORIGINS``
    **Required.** Comma-separated list of allowed CORS origins for API requests

    - **Default:** None
    - **Example:** ``JUNJO_ALLOW_ORIGINS=https://junjo.example.com,https://www.example.com``

``JUNJO_SESSION_SECRET``
    **Required for production.** Secret key for session management and JWT tokens

    - **Default:** None
    - **Example:** ``JUNJO_SESSION_SECRET=a1b2c3d4e5f6...`` (64 character hex string)
    - **Generate with:** ``openssl rand -hex 32``

``JUNJO_PROD_AUTH_DOMAIN``
    **Required for production.** The primary domain for authentication cookies

    - **Default:** None
    - **Example:** ``JUNJO_PROD_AUTH_DOMAIN=junjo.example.com``

``JUNJO_BUILD_TARGET``
    **Optional.** Build target for development purposes

    - **Default:** ``production``
    - **Example:** ``JUNJO_BUILD_TARGET=development``

Ingestion Service
~~~~~~~~~~~~~~~~~

``JUNJO_SERVER_API_KEY``
    **Required.** API key for authenticating telemetry ingestion requests

    - **Default:** None
    - **Example:** ``JUNJO_SERVER_API_KEY=js_1234567890abcdef...``
    - **Generate:** Create in the Junjo Server web UI under Settings → API Keys

Frontend Service
~~~~~~~~~~~~~~~~

``VITE_API_URL``
    **Optional.** Backend API URL for the frontend to connect to

    - **Default:** ``http://localhost:1323`` (development)
    - **Example:** ``VITE_API_URL=https://api.junjo.example.com``
    - **Note:** In production with reverse proxy, this may be a relative path

Volume Mounts
-------------

All three services require persistent storage for their databases. The recommended approach is to use either local directories or block storage volumes.

Local Directory Structure
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

    .
    ├── docker-compose.yml
    ├── .env
    └── dbdata/
        ├── sqlite/       # Backend metadata
        ├── duckdb/       # Backend analytics
        └── badgerdb/     # Ingestion WAL

**Create directories:**

.. code-block:: bash

    mkdir -p dbdata/{sqlite,duckdb,badgerdb}
    chmod -R 755 dbdata

Block Storage (Production)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For production deployments, mount block storage at a consistent location:

.. code-block:: bash

    # Example: Mount block storage
    sudo mkfs.ext4 /dev/disk/by-id/scsi-0DO_Volume_junjo-data
    sudo mkdir -p /mnt/junjo-data
    sudo mount -o defaults,nofail /dev/disk/by-id/scsi-0DO_Volume_junjo-data /mnt/junjo-data

    # Create database directories
    sudo mkdir -p /mnt/junjo-data/{sqlite,duckdb,badgerdb}
    sudo chown -R $USER:$USER /mnt/junjo-data

Update volume paths in docker-compose.yml:

.. code-block:: yaml

    volumes:
      - /mnt/junjo-data/sqlite:/dbdata/sqlite
      - /mnt/junjo-data/duckdb:/dbdata/duckdb
      - /mnt/junjo-data/badgerdb:/dbdata/badgerdb

Port Mappings
-------------

Internal Communication
~~~~~~~~~~~~~~~~~~~~~~

Services communicate internally via the Docker network. These ports do not need to be exposed to the host:

.. code-block:: text

    Backend (1323) ←→ Frontend
    Backend (50053) ←→ Ingestion (50052)

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
- Ingestion: ``grpc.junjo.example.com:443`` (gRPC with TLS)

See :doc:`deployment` for production deployment examples with Caddy reverse proxy.

Resource Requirements
---------------------

Junjo Server is designed to run on minimal resources:

**Minimum:**

- **CPU:** 1 shared vCPU
- **RAM:** 1 GB
- **Storage:** 10 GB (more for long-term trace retention)

**Recommended for Production:**

- **CPU:** 1-2 dedicated vCPUs
- **RAM:** 2-4 GB
- **Storage:** 25+ GB on block storage
- **Network:** 1 Gbps

Database Sizes
~~~~~~~~~~~~~~

- **BadgerDB (Ingestion):** Write-ahead log, periodically compacted
- **SQLite (Backend):** Metadata and indexes, grows slowly
- **DuckDB (Backend):** Analytical data, grows with trace retention

Network Configuration
---------------------

Docker Network
~~~~~~~~~~~~~~

All services should run on the same Docker network for internal communication:

.. code-block:: yaml

    networks:
      junjo-network:
        driver: bridge

Firewall Rules
~~~~~~~~~~~~~~

If using a firewall, allow these ports:

- ``1323/tcp`` - Backend API (if accessing directly)
- ``5153/tcp`` - Frontend web UI
- ``50051/tcp`` - Ingestion gRPC endpoint
- ``443/tcp`` - HTTPS (if using reverse proxy)
- ``80/tcp`` - HTTP (for Let's Encrypt challenges)

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

    # Web UI
    junjo.example.com {
        reverse_proxy junjo-server-frontend:80
    }

    # Backend API
    api.junjo.example.com {
        reverse_proxy junjo-server-backend:1323
    }

    # Ingestion gRPC
    grpc.junjo.example.com {
        reverse_proxy h2c://junjo-server-ingestion:50051
    }

See the `Junjo Server Deployment Example <https://github.com/mdrideout/junjo-server-deployment-example>`_ for a complete production setup.

Backup and Recovery
~~~~~~~~~~~~~~~~~~~

Backup all three database directories regularly:

.. code-block:: bash

    # Backup script example
    tar -czf junjo-backup-$(date +%Y%m%d).tar.gz \
        dbdata/sqlite \
        dbdata/duckdb \
        dbdata/badgerdb

To restore, stop services, extract backup, and restart:

.. code-block:: bash

    docker compose down
    tar -xzf junjo-backup-20241012.tar.gz
    docker compose up -d

Monitoring
~~~~~~~~~~

Monitor these key metrics:

- **Disk usage:** Database directories
- **Memory usage:** Each service container
- **Network traffic:** Port 50051 (ingestion load)
- **API response time:** Backend health endpoint
- **Error logs:** ``docker compose logs``

Health Checks
~~~~~~~~~~~~~

Services include health check endpoints:

- **Backend:** ``http://localhost:1323/health``
- **Ingestion:** gRPC health probe on port 50051

Example monitoring with curl:

.. code-block:: bash

    # Check backend health
    curl http://localhost:1323/health

    # Check all services
    docker compose ps

Scaling Considerations
----------------------

Horizontal Scaling
~~~~~~~~~~~~~~~~~~

For high-volume deployments:

1. **Ingestion Service:** Can run multiple instances behind a load balancer
2. **Backend Service:** Can run multiple instances with shared database volumes
3. **Frontend Service:** Static assets, easily cached or CDN-distributed

Example multi-instance configuration:

.. code-block:: yaml

    services:
      junjo-server-ingestion:
        image: mdrideout/junjo-server-ingestion-service:latest
        deploy:
          replicas: 3
        # ... rest of configuration

Vertical Scaling
~~~~~~~~~~~~~~~~

For most deployments, vertical scaling is sufficient:

- Increase CPU/RAM allocation
- Use faster disk (NVMe SSDs)
- Increase Docker memory limits

.. code-block:: yaml

    services:
      junjo-server-backend:
        # ... existing config
        deploy:
          resources:
            limits:
              cpus: '2'
              memory: 4G
            reservations:
              cpus: '1'
              memory: 2G

Troubleshooting
---------------

Service Won't Start
~~~~~~~~~~~~~~~~~~~

Check logs for specific errors:

.. code-block:: bash

    docker compose logs junjo-server-backend
    docker compose logs junjo-server-ingestion
    docker compose logs junjo-server-frontend

Common issues:

- Missing environment variables in ``.env``
- Port conflicts (check with ``netstat -tlnp``)
- Permission issues with volume mounts
- Network not created (``docker network create junjo-network``)

High Memory Usage
~~~~~~~~~~~~~~~~~

If services consume excessive memory:

- Check BadgerDB size (``du -sh dbdata/badgerdb``)
- Implement trace retention policies
- Increase disk swap if needed
- Add memory limits to docker-compose.yml

Cannot Connect to Ingestion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If applications can't send telemetry:

- Verify port 50051 is accessible: ``telnet localhost 50051``
- Check firewall rules
- Verify API key in application matches server
- Check ingestion service logs for auth errors

API Errors
~~~~~~~~~~

If the web UI shows API errors:

- Check CORS settings in backend (``JUNJO_ALLOW_ORIGINS``)
- Verify frontend can reach backend API
- Check backend logs for specific errors
- Verify session secret is set in production

Next Steps
----------

- See :doc:`junjo_server` for setup and configuration
- Review :doc:`deployment` for production deployment examples
- Explore :doc:`opentelemetry` for application instrumentation