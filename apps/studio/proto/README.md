# Proto Schemas

This directory contains all Protocol Buffer definitions for the Junjo AI Studio project.

## Schema Types

### Service API Schemas (gRPC)
These define the internal gRPC service interfaces between the backend and ingestion:
- **`ingestion.proto`**: `InternalIngestionService` (`PrepareHotSnapshot`, `FlushWAL`). Ingestion implements it and the backend calls it.
- **`auth.proto`**: `InternalAuthService` (`ValidateApiKey`). The backend implements it and ingestion calls it.

Both files use `package ingestion;`, so each service compiles them into one generated module.

### Internal Storage Schemas
These are not part of the gRPC service APIs:
- **`span_data_container.proto`**: Legacy internal-only schema from an older ingestion storage layer. Neither
  service compiles it. The current Rust ingestion path uses Arrow IPC WAL + Parquet.

## Generation Tools

No generated code is checked in. Both services are Rust and generate at build time with `tonic-prost-build`:
- **Backend**: `backend/server/build.rs`
- **Ingestion**: `ingestion/build.rs`

Each build script lists the proto files it compiles and needs the pinned `protoc`. See
[`PROTO_VERSIONS.md`](../PROTO_VERSIONS.md) for the version and where it is pinned.

## Schema Lifecycle Management

### Adding New Proto Files
1. Create `.proto` file in this directory
2. Add it to the build script of each service that uses it
3. Validate both services: run `cargo test --locked` in `backend/` and in `ingestion/`

### Modifying Existing Protos
1. Update the `.proto` file
2. Update the backend and ingestion in the same change. They compile the same files and are released together
3. Validate both services (same as above)

### Deleting Proto Files
1. Remove the file from each build script that lists it
2. Remove the code that uses its generated types
3. Validate both services (same as above)

## Schema Versioning

Proto schemas support backward-compatible evolution:
- **Add fields**: Safe (use new field numbers)
- **Remove fields**: Mark as `reserved` instead
- **Rename fields**: Use `json_name` annotation
- **Change types**: Usually unsafe
