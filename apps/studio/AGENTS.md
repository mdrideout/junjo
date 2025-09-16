# Junjo Server: System Architecture for LLM Agents

This document provides a high-level overview of the Junjo Server architecture, designed to help LLM agents quickly understand the system's components and interaction flows.

## 1. System Overview

The Junjo Server is a multi-service system designed for ingesting, storing, and analyzing OpenTelemetry (OTel) data. It consists of two primary backend services and client-side telemetry collection via the Junjo Otel Exporter.

*   **`backend`**: The main application server. It handles user authentication, provides the API and web UI, and processes telemetry data for analysis.
*   **`ingestion-service`**: A dedicated, high-throughput service responsible for receiving OTel data from clients and persisting it to a Write-Ahead Log (WAL).
*   **Junjo Otel Exporter**: A specialized OpenTelemetry exporter that sends telemetry data to the ingestion-service.

## 2. Component Architecture

The services are designed to be decoupled, with specific responsibilities to ensure scalability and resilience.

```mermaid
graph TD
    subgraph "ingestion-service"
        C(Internal gRPC API) -->|Reads| B{BadgerDB WAL}
        A(gRPC Server) -->|Writes| B
        I(Auth Service) -->|Forwards Auth| J[Backend Internal Auth]
    end

    subgraph "backend"
        D(Ingestion Client) -->|gRPC Internal| C
        D -->|Processes & Batches| E(OTel Span Processor)
        E -->|Indexes| F{DuckDB}
        E -->|Vectorizes & Stores| H{QDrant}
        J -->|Validates API Key & Generates JWT| K[JWT Token]
    end

    subgraph "clients"
        G(Junjo Otel Exporter) -->|OTel Data| A
        G -->|API Key| I
    end

    style A fill:#d4edda,stroke:#155724
    style C fill:#cce5ff,stroke:#004085
    style D fill:#cce5ff,stroke:#004085
    style G fill:#fff3cd,stroke:#856404
    style I fill:#f8d7da,stroke:#721c24
    style J fill:#cce5ff,stroke:#004085
```

### `backend` Service

*   **Responsibilities**:
    *   Serves the main web UI and REST API on port `1323`.
    *   Manages user accounts and API keys.
    *   Acts as the **Identity Provider** for the system. It issues JSON Web Tokens (JWTs) to clients via a private gRPC endpoint.
    *   Publishes a JSON Web Key Set (JWKS) at `/.well-known/jwks.json` for JWT signature verification.
    *   Reads data from the `ingestion-service` to index it into a queryable database (DuckDB) and vector store (QDrant).
*   **Internal Authentication Endpoint**:
    *   `J[Backend Internal Auth]`: Private gRPC endpoint for validating API keys and generating JWT tokens for clients.
    *   Publishes a JSON Web Key Set (JWKS) at `/.well-known/jwks.json` for JWT signature verification.
*   **Key Files**:
    *   [`backend/main.go`](backend/main.go): Main application entry point.
    *   [`backend/api/otel_token/`](backend/api/otel_token/): Logic for the JWT exchange endpoint.
    *   [`backend/jwks/jwks.go`](backend/jwks/jwks.go): Logic for the JWKS endpoint.

### `ingestion-service`

*   **Responsibilities**:
    *   Exposes a public gRPC server on port `50051` that serves as the single point of contact for clients.
    *   Provides an `AuthService` for clients to exchange an API key for a JWT.
    *   Forwards authentication requests to the `backend` over a private gRPC connection.
    *   **Enforces Authentication**: Protects its OTel endpoints using a JWT interceptor. It validates tokens against the `backend`'s JWKS endpoint.
    *   Persists all incoming data to a highly-performant Write-Ahead Log (WAL) using BadgerDB.
*   **Key Files**:
    *   [`ingestion-service/main.go`](ingestion-service/main.go): Main application entry point.
    *   [`ingestion-service/server/server.go`](ingestion-service/server/server.go): gRPC server setup.
    *   [`ingestion-service/server/auth_service.go`](ingestion-service/server/auth_service.go): The public-facing authentication service.
    *   [`ingestion-service/backend_client/auth_client.go`](ingestion-service/backend_client/auth_client.go): The client for the backend's internal auth service.
    *   [`ingestion-service/server/jwt_interceptor.go`](ingestion-service/server/jwt_interceptor.go): The JWT authentication logic.
    *   [`ingestion-service/jwks/jwks.go`](ingestion-service/jwks/jwks.go): The client for fetching the JWKS.

## 3. Authentication Flow (JWT-based)

Authentication is handled via a token exchange mechanism, facilitated by the `ingestion-service` to provide a single point of contact for the client.

```mermaid
sequenceDiagram
    participant Client as OTel SDK Client
    participant Ingestion as ingestion-service
    participant Backend as backend

    Client->>Ingestion: 1. Request JWT via gRPC (AuthService.GetToken, API Key)
    activate Ingestion
    Ingestion->>Backend: 2. Forward request via internal gRPC (ExchangeApiKeyForJwt)
    activate Backend
    Backend->>Backend: 3. Validate API Key & Generate JWT
    Backend-->>Ingestion: 4. Return JWT
    deactivate Backend
    Ingestion-->>Client: 5. Return JWT
    deactivate Ingestion

    loop OTel Data Export
        Client->>Ingestion: 6. Send OTel data via gRPC (Metadata: `Authorization: Bearer <jwt>`)
        activate Ingestion
        Ingestion->>Ingestion: 7. Interceptor validates JWT (using JWKS)
        alt JWT KID not cached
            Ingestion->>Backend: 8. Fetch JWKS
            activate Backend
            Backend-->>Ingestion: 9. Return Public Key Set
            deactivate Backend
        end
        Ingestion->>Ingestion: 10. Write data to WAL
        Ingestion-->>Client: 11. Success
        deactivate Ingestion
    end
```

### Step-by-Step Process:

1.  **Token Exchange**: The client makes a gRPC call to the `ingestion-service`'s `AuthService.GetToken` method, providing its API key.
2.  **Internal Forwarding**: The `ingestion-service` receives this request and forwards it to the `backend`'s internal `InternalAuthService.ExchangeApiKeyForJwt` method via a private gRPC connection.
3.  **JWT Issuance**: The `backend` validates the API key. If valid, it generates a new RSA256-signed JWT and returns it to the `ingestion-service`.
4.  **Token Response**: The `ingestion-service` passes the JWT back to the client.
5.  **Authenticated Export**: The client configures its OTel gRPC exporter to include the JWT in the metadata of every outgoing request to the `ingestion-service`. The header is `Authorization: Bearer <jwt>`.
6.  **Token Validation**: The `ingestion-service`'s `JWTInterceptor` catches every incoming request.
7.  **JWKS Fetch**: The interceptor checks the token's signature. To do this, it needs the public key. It fetches the key from the `backend`'s `/.well-known/jwks.json` endpoint, identifying the correct key via the `kid` (Key ID) in the JWT header.
8.  **Reactive Key Rotation**: The JWKS client in the `ingestion-service` is reactive. If it sees a `kid` it doesn't have a key for, it automatically refetches the JWKS from the `backend`. This allows the `backend` to rotate its signing keys without requiring a restart of the `ingestion-service`.
9.  **Access Control**: If the JWT is valid and unexpired, the request is allowed to proceed. Otherwise, it is rejected with an `Unauthenticated` error.

## 4. Data Flow: WAL and Indexing

The `ingestion-service` acts as a Write-Ahead Log (WAL) for the main `backend`. This decouples the high-throughput ingestion of OTel data from the more resource-intensive process of indexing that data for querying.

### Step-by-Step Process:

1.  **Write to WAL**: The `ingestion-service` receives OTel data via its public gRPC endpoint and immediately writes the raw, serialized data to a BadgerDB WAL. This is a fast, append-only operation.

2.  **Internal Read API**: The `ingestion-service` exposes a second, internal-only gRPC service (`WALReaderService`) that allows the `backend` to read data from the WAL in batches.

3.  **Client Polling**: The `backend`'s `ingestion_client` periodically polls the `WALReaderService`, requesting a batch of spans starting from the last key it successfully processed.

4.  **State Management**: The `backend` is responsible for persisting the key of the last span it indexed. This ensures that if the `backend` restarts, it can resume processing from where it left off without missing any data.

5.  **Processing and Indexing**: Once the `backend` receives a batch of spans, it uses its `otel_span_processor` to deserialize, process, and index the data into a DuckDB database and vector store (QDrant), making it available for querying via the main API.

This pull-based architecture makes the system resilient. The `ingestion-service` can continue to accept data even if the `backend` is temporarily down or slow to index.