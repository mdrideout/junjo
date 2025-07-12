# Project Server: Junjo Server

This repository services as the Project Server's Junjo Server instance.

This Junjo Server instance should be capable of being used for all projects that may use Junjo on this server.

## Deployment

This repository is designed to be deployed to a webserver running a reverse proxy to its services.

### Caddy Caddyfile Example

The following Caddyfile would be used to serve all of Junjo Server's services.

_Note the use of junjo.example.com and the wildcard *.junjo.example.com for subdomain services._

```
# ----------------------------------------------------------------------------------------
# Production Domain & Subdomains
#   Name        Container Name & Port           Access URL
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
