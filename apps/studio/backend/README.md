# Junjo-UI Backend

This is the backend GO Echo server container of the Junjo-UI setup.

## Code Generation

### sqlc

This project uses [sqlc](https://sqlc.dev/) to compile type-safe code from SQL.

```bash
# Generate GO code from SQL (from ./backend)
$ sqlc generate
```

### Protobuf

This server receives telemetry from the junjo library via gRPC. The following instructions generate the gRPC service from `.proto` file code.

**Requires:** [protoc](https://grpc.io/docs/protoc-installation/) which can be installed into your developer environment host machine ([instructions](https://grpc.io/docs/protoc-installation/)).

```bash
# Run the makefile to generate the code
$ make proto
```