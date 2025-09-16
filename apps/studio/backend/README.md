# GO API & Telemetry Server

This is the backend GO application running in a docker container of the junjo-server setup.

**Servers:** This GO application runs two servers.

- GO Echo server: React UI application API requests
- gRPC server: Receives and handles telemetry from the junjo library


## Code Generation

### Database Migrations & Code Generation

This project uses [Goose](https://github.com/pressly/goose) for database migrations and [sqlc](https://sqlc.dev/) to compile type-safe Go code from SQL queries.

The database schema is defined through migration files in `db/migrations/`. When you make changes to these migrations, you should regenerate the Go code to keep it in sync:

```bash
# Regenerate Go database code from migrations (from ./backend)
$ make db-regenerate
```

This command will:
1. Apply all migrations to a temporary in-memory database
2. Dump the resulting schema to `db/schema.sql`
3. Generate Go code from the updated schema using sqlc

If you need to create a new migration file:

```bash
# Create a new migration file (from ./backend)
$ make db-new-migration name=your_migration_name
```

### sqlc

You can also run sqlc generation independently:

```bash
# Generate GO code from SQL (from ./backend)
$ make sqlc-generate

# or directly with sqlc
$ sqlc generate
```

### Protobuf

This server receives telemetry from the junjo library via gRPC. The following instructions generate the gRPC service from `.proto` file code.

**Requires:** [protoc](https://grpc.io/docs/protoc-installation/) which can be installed into your developer environment host machine ([instructions](https://grpc.io/docs/protoc-installation/)).

```bash
# Run the makefile to generate the code
$ make proto
```

#### NOTE:

`.proto` files between junjo and junjo-server must match.