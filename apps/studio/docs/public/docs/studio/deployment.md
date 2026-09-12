---
title: "Self-host Junjo AI Studio with Docker Compose"
description: "Deploy lightweight Studio services, preserve your datasets and telemetry, and connect your application and coding agent for recursive self improvement."
---

Junjo AI Studio runs as three lightweight containerized services: the
frontend, backend, and ingestion service. Deploy them alongside your application
or on a separate host. Your application runs its own models, tools, and
evaluators; Studio stores the shared experiment data and execution evidence.

## Minimal Build Template (Recommended Starting Point)

Use the [Junjo AI Studio minimal distribution](https://github.com/mdrideout/junjo-ai-studio-minimal-build)
for local development or an existing Docker Compose environment. It contains
versioned images, a configuration example, and a setup script. Bring your own
reverse proxy and TLS when making the services remotely accessible.

1. Clone or download the distribution.
2. Run its `./scripts/junjo setup` wizard. Choose the environment and memory
   profile; it generates the required secrets and reports your service URLs.
   The distribution's README also documents manual `.env` setup.
3. Start it with `docker compose up -d` from the distribution directory.
4. Open the web UI at the address printed by setup. With default local host
   ports, this is `http://localhost:26153`.

For an existing Compose stack, use the distribution's versioned Compose file
as the configuration source. Preserve the backend/ingestion shared storage,
private RPC settings, and service-specific environment overrides. The
[Docker reference](/docs/studio/docker-reference/) explains these boundaries.

The standalone repository is a generated release distribution. Its canonical
source is [apps/studio/deployments/minimal](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/minimal)
in the Junjo monorepo. Download a supported release and follow that release's
files; copying an older Compose snippet can lose required configuration.

## Digital Ocean VM Deployment Example

The [VM/Caddy distribution](https://github.com/mdrideout/junjo-ai-studio-deployment-example)
walks through a fresh VM, DNS, Docker Compose, persistent storage, and automatic
HTTPS. It includes the three Studio services and Caddy routing for:

| Destination | Example public address |
| --- | --- |
| Studio web UI | `https://junjo.example.com` |
| Backend API for browser, CLI, and SDK | `https://api.junjo.example.com` |
| OTLP/gRPC ingestion | `https://ingestion.junjo.example.com` |

Studio runs well on a 1GB RAM VM with the supported small-host profile. Model
inference and evaluation execution remain in your application environment.
Size persistent storage for your actual trace volume and retained history;
the VM size is a practical starting point, not a throughput benchmark.

Use the distribution's setup and Caddy configuration together. In production,
the frontend and backend must share a registrable domain for Studio's browser
session cookies. The canonical source lives in
[apps/studio/deployments/vm-caddy](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/vm-caddy).

## Connect your application and coding agent

Studio has two independent connections. Configure both before asking your
coding agent to perform a recursive self improvement cycle.

### Send application telemetry

Sign in to Studio and create a key in **API Keys**. Give the application that
key as `JUNJO_AI_STUDIO_API_KEY`; the OTLP exporter sends it in the
`x-junjo-api-key` header to **ingestion**.

Select the destination for the application's actual network:

| Application location | Default minimal-distribution ingestion destination |
| --- | --- |
| On the same local host | `localhost:26155` |
| Container on the Studio Compose network | `junjo-ai-studio-ingestion:26155` |
| Another host | Your configured public OTLP/gRPC endpoint with TLS |

Host-port overrides affect the localhost address. Containers on the shared
Compose network keep the service's container port. Inside an application
container, `localhost` refers to that container.

Follow the [OpenTelemetry setup guide](/docs/observability/opentelemetry/) for
application-owned tracing and lifecycle configuration. For an OpenAI Agents
application, follow the [first-party integration guide](/docs/python/integrations/openai-agents/).

### Give the coding agent evaluation and evidence access

Open **Access Tokens** in Studio and create a developer access token with the
scopes needed for the task:

- `evaluation:read` to inspect datasets and run results.
- `evaluation:write` to create cases and record experiments.
- `evidence:read` to investigate execution evidence.

Configure `JUNJO_AI_STUDIO_CLI_TOKEN` with that token and
`JUNJO_AI_STUDIO_BACKEND_BASE_URL` with the **backend API origin**. With the
default local distribution, the origin is `http://localhost:26154`. For a
remote deployment, use its HTTPS API origin, such as
`https://api.junjo.example.com`.

The SDK accepts plain HTTP only for loopback. A VM address or Docker service
hostname is not loopback; use HTTPS for that control connection, or a local
forwarded loopback endpoint. This is independent of OTLP/gRPC transport setup.

The developer token does not authorize trace ingestion, and an ingestion API
key does not authorize evaluation or evidence queries. Keep both outside
application source and copied investigation reports.

Install the matching Junjo SDK in the application environment and make its
packaged evaluation skill available to your coding agent. The
[evaluation guide](/docs/python/evaluation/#give-a-coding-agent-the-runbook)
owns the skill installation and application harness setup.

### Verify both connections

1. Execute a small instrumented application request. Let its telemetry
   provider finish exporting, then find the expected service and trace in
   Studio. Check an intermediate operation you will need to diagnose.
2. With the developer token, ask the coding agent to list datasets through
   `junjo eval`. An empty successful list verifies access on a new instance.
3. Follow the [dataset and run guide](/docs/python/evaluation/) to create the
   first dataset and run. Confirm that the coding agent can read that record
   and that its **View spans** link opens the corresponding execution in Studio.

An application can finish before its evidence is queryable. Treat a pending
evidence response as delivery still to verify; a local exporter flush result
alone is not proof of remote storage.

## Preserve the experiment history

Backend and ingestion use the same persistent host data directory. It holds
canonical accounts, credentials, datasets, runs, and results as well as trace
storage and the telemetry index. Preserve the whole data directory and the
deployment configuration when moving or replacing containers.

Before an upgrade, read the chosen release's compatibility and migration
instructions and take a consistent backup. Some greenfield releases require
an explicit data reset. Treat that as a release-specific destructive step,
not a routine way to troubleshoot service startup.

For existing block storage, mount the existing filesystem and point
`JUNJO_HOST_DB_DATA_PATH` to it. Formatting a disk destroys its contents; it
is only part of deliberately provisioning an empty volume. See the
[storage reference](/docs/studio/docker-reference/#volume-mounts).

## Continue with your first improvement

Use [recursive self improvement](/docs/recursive-self-improvement/) to connect
diagnosis, targeted scenarios, local experiments, and human review. The
[Studio investigation guide](/docs/studio/overview/) shows how your coding
agent's findings link back to the records your team can inspect.
