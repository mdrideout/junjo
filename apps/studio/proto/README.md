# Proto Schemas

This directory contains all Protocol Buffer definitions for the Junjo AI Studio project.

## Schema Types

### Service API Schemas (gRPC)
These define the gRPC service interfaces between components:
- **`ingestion.proto`**: Internal API for backend → ingestion communication (span reading)
- **`auth.proto`**: Authentication service definitions

### Internal Storage Schemas
These are used only for internal data persistence and are not part of service APIs:
- **`span_data_container.proto`**: SQLite WAL storage format for spans + resources (ingestion service only)

## Important: Schema Lifecycle Management

### Adding New Proto Files
1. Create `.proto` file in this directory
2. Regenerate code for all consumers:
   ```bash
   cd ingestion && make proto
   cd backend && ./scripts/generate_proto.sh
   ```
3. Verify schemas are valid: `cd ingestion && make proto-check-orphans`

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
1. Check if it's used for storage (SQLite WAL, DuckDB, etc.)
2. If yes: Migrate existing data to new schema first
3. Remove all references in code
4. Clean and regenerate: `cd ingestion && make proto-clean`
5. Verify: `cd ingestion && make proto-check-orphans`

## Schema Orphaning Prevention

The `ingestion/Makefile` includes a `proto-check-orphans` target that checks for "orphaned schemas" - where generated `.pb.go` files exist but their source `.proto` files are missing.

This was added after [commit 3be9fec](https://github.com/anthropics/junjo-ai-studio/commit/3be9fec) accidentally deleted `span_data_container.proto` during proto consolidation, causing storage corruption.

**Run verification after any proto refactoring**:
```bash
cd ingestion
make proto-check-orphans
```

**Full validation pipeline** (recommended after refactoring):
```bash
cd ingestion
make proto-full-validation
```
This runs: clean → regenerate → check for orphans

## Generation Tools

- **Go** (ingestion): Uses `protoc` with `go` and `go-grpc` plugins
  - Version controlled in `ingestion/Makefile`
  - Generate: `cd ingestion && make proto`

- **Python** (backend): Uses `grpc_tools.protoc`
  - Script: `backend/scripts/generate_proto.sh`
  - Generate: `cd backend && ./scripts/generate_proto.sh`

## Schema Versioning

Proto schemas support backward-compatible evolution:
- **Add fields**: Safe (use new field numbers)
- **Remove fields**: Mark as `reserved` instead
- **Rename fields**: Use `json_name` annotation
- **Change types**: Usually unsafe - requires migration

For storage schemas (like `span_data_container.proto`), changes may require data migration or reconciliation logic.
