# Junjo Server - Standalone Deployment

This repository is a self-contained deployable docker compose setup for [Junjo Server](https://github.com/mdrideout/junjo-server).

A Junjo Server instance can be used for all an unlimited number of projects that use the [Junjo](https://github.com/mdrideout/junjo) python AI graph workflow framework.

This docker compose project is designed to be deployed to a webserver running a reverse proxy to the services in this `docker-compose.yml` file. Any Junjo Application can send telemetry to this Junjo Server, assuming it has valid API Key credentials.

> #### Full E2E Junjo Application Example:
>
>To see an example deployment that includes a python application that uses the Junjo library to execute a graph workflow and sends telemetry to Junjo Server, see this [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

## Junjo Server Deployment

Below are deployment configuration explanations and examples to help you route your server's incoming traffic to the Junjo Server services.

### Reverse Proxy

This repository contains no affordances for a reverse proxy, so you will need to configure your own. I recommend [**Caddy**](https://caddyserver.com/), **Nginx**, or **Traefik** are also popular.

### Exposed Services

_Note: It is the responsibility of your reverse proxy to route incoming traffic to the correct Junjo Server services and ports._

| Service  | Docker Container & Internal Port | Example URL                      |
|----------|----------------------------------|----------------------------------|
| Frontend | junjo-server-frontend:5153   		| https://junjo.example.com        |
| Jaeger   | junjo-jaeger:16686           		| https://junjo.example.com/jaeger |
| Backend  | junjo-server-backend:1323    		| https://api.junjo.example.com    |
| gRPC     | junjo-server-backend:50051   		| https://grpc.junjo.example.com   |

### Caddy Server Example

If you are using [Caddy Server](https://caddyserver.com/), below is an example Caddyfile that servces all of Junjo Server's services.

- _Note the use of `junjo.example.com` and the wildcard `*.junjo.example.com` for subdomain services._
- _Example incorporates [cloudflare SSL certificate handling](https://github.com/caddy-dns/cloudflare)._
- _See Caddy [https quick-start](https://caddyserver.com/docs/quick-starts/https) for other methods._
- _Requires a Wildcard A record for `*.junjo.example.com` in your DNS provider._

#### Caddyfile
```
# ----------------------------------------------------------------------------------------
# Production Domain & Subdomains
#   Name        Container Name & Internal Port 	Access URL
# - Frontend:   junjo-server-frontend:5153      https://junjo.example.com
# - Jaeger      junjo-jaeger:16686              https://junjo.example.com/jaeger
# - Backend:    junjo-server-backend:1323       https://api.junjo.example.com
# - gRPC:       junjo-server-backend:50051      https://grpc.junjo.example.com
# ----------------------------------------------------------------------------------------
junjo.example.com, *.junjo.example.com {
	# For automatic SSL (via xcaddy cloudflare plugin)
	tls {
		dns cloudflare {$CF_API_TOKEN} # Created inside CloudFlare and set in the .env file
		resolvers 1.1.1.1 # Cloudflare DNS is recommended for this plugin
	}

	# API Backend: api.junjo.example.com
	@api host api.junjo.example.com
	handle @api {
		reverse_proxy junjo-server-backend:1323
	}

	# gRPC Backend: grpc.junjo.example.com
	@grpc host grpc.junjo.example.com
	handle @grpc {
		reverse_proxy junjo-server-backend:50051
	}

	# Handle Jaeger UI requests with forward authentication.
	@jaegerPath path /jaeger*
	handle @jaegerPath {
		# Validate all jaeger requests with the backend auth service (validates cookies)
		forward_auth junjo-server-backend:1323 {
			uri /auth-test
			copy_headers Cookie

			# Redirect to the FE app sign-in page if the auth service returns a 4xx status
			@bad status 4xx
			handle_response @bad {
				redir https://junjo.example.com/sign-in 302
			}
		}

		# If auth succeeds (200 response), continue the request to the Jaeger UI.
		reverse_proxy junjo-jaeger:16686
	}

	# Fallback for the root domain
	handle {
		reverse_proxy junjo-server-frontend:80
	}
}
```

## Junjo Application Telemetry Configuration

[Junjo's python library](https://python-api.junjo.ai/) uses OpenTelemetry to send structured AI graph workflow execution spans to Junjo Server or any other OpenTelemetry destination.

Below is an example of a Junjo Application's OpenTelemetry configuration that sends telemetry to Junjo Server.  Note the `JunjoServerOtelExporter` configuration, which uses Junjo Server's gRPC endpoint and TLS secured port.

You can also check out this [End-To-End Junjo App + Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

```python
import os

from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

def setup_telemetry():
	"""
	Sets up the OpenTelemetry tracer and exporter.
	"""

	# Load the JUNJO_SERVER_API_KEY from the environment variable
	JUNJO_SERVER_API_KEY = os.getenv("JUNJO_SERVER_API_KEY")
	if JUNJO_SERVER_API_KEY is None:
		print(
			"JUNJO_SERVER_API_KEY environment variable is not set. "
			"Generate a new API key in the Junjo Server UI."
		)
		return

	# Configure OpenTelemetry for this application
	# Create the OpenTelemetry Resource to identify this service
	resource = Resource.create({"service.name": "Junjo Deployment Example"})

	# Set up tracing for this application
	tracer_provider = TracerProvider(resource=resource)

	# Option 1: Assuming this application is on a different server
	# Construct a Junjo exporter for Junjo Server
	junjo_server_exporter = JunjoServerOtelExporter(
		host="grpc.junjp.example.com",
		port="443",
		api_key=JUNJO_SERVER_API_KEY,
		insecure=False,
	)

	# Option 2: Assuming this application is on the same server and same docker network
	# Construct a Junjo exporter for Junjo Server
	# junjo_server_exporter = JunjoServerOtelExporter(
	# 	host="junjo-server-backend",
	# 	port="50051",
	# 	api_key=JUNJO_SERVER_API_KEY,
	# 	insecure=True,
	# )

	# Set up span processors
	# Add the Junjo span processor (Junjo Server and Jaeger)
	# Add more span processors if desired
	tracer_provider.add_span_processor(junjo_server_exporter.span_processor)
	trace.set_tracer_provider(tracer_provider)

	return
```