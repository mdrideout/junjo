# Proto Schemas

This directory contains all Protocol Buffer definitions for the Junjo AI Studio project.

## Schema Types

### Service API Schemas (gRPC)
These define the gRPC service interfaces between components:
- **`ingestion.proto`**: Backend → ingestion internal RPCs (e.g. `PrepareHotSnapshot`, `FlushWAL`)
- **`auth.proto`**: Ingestion → backend internal RPCs (e.g. `ValidateApiKey`)

### Internal Storage Schemas
These are not part of the gRPC service APIs:
- **`span_data_container.proto`**: Legacy internal-only schema from an older ingestion storage layer. The
  current Rust ingestion path uses Arrow IPC WAL + Parquet and does not depend on this schema at runtime.

## Important: Schema Lifecycle Management

### Adding New Proto Files
1. Create `.proto` file in this directory
2. Regenerate code for all consumers:
   ```bash
   cd backend && ./scripts/generate_proto.sh
   cd ingestion && cargo check
   ```
3. Commit updated Python stubs in `backend/app/proto_gen/`

### Modifying Existing Protos
1. Update the `.proto` file
2. Regenerate code (same as above)
3. Consider backward compatibility for production data
4. **For storage schemas**: May require data migration if format changes

### Deleting Proto Files
⚠️ **DANGER**: Deleting proto files can cause production issues if:
- Generated code still references the schema
- Persisted data was written using the schema

**Before deleting a proto**:
1. Check if it's used for storage (legacy ingestion formats, etc.)
2. If yes: Migrate existing data to new schema first
3. Remove all references in code
4. Regenerate Python stubs: `cd backend && ./scripts/generate_proto.sh`
5. Validate builds/tests: `cd ingestion && cargo test`

## Generation Tools

- **Rust** (ingestion): Generated at build time via `ingestion/build.rs` (no committed generated files)
- **Python** (backend): Generated via `grpc_tools.protoc`
  - Script: `backend/scripts/generate_proto.sh`
  - Generate: `cd backend && ./scripts/generate_proto.sh`

## Schema Versioning

Proto schemas support backward-compatible evolution:
- **Add fields**: Safe (use new field numbers)
- **Remove fields**: Mark as `reserved` instead
- **Rename fields**: Use `json_name` annotation
- **Change types**: Usually unsafe - requires migration

For storage schemas (like `span_data_container.proto`), changes may require data migration or reconciliation logic.
