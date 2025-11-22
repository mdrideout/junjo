# Protocol Buffer Tool Versions

This document specifies the **locked versions** of Protocol Buffer tools used in this project.
These versions MUST match the ones used in `junjo-ai-studio` to ensure compatibility.

## Required Tool Versions

| Tool | Version | Purpose |
|------|---------|---------|
| **protoc** | v30.2 | Protocol Buffer compiler (system-installed) |
| **grpcio-tools** | 1.76.0 | Python protobuf/gRPC code generator |

## Why Lock Versions?

Different versions of `protoc` and its plugins generate structurally different code.
By locking to the same version used in our backend services, we ensure:

1.  **Compatibility:** The generated SDK code works seamlessly with our ingestion services.
2.  **Consistency:** CI validation passes without "diff noise" caused by minor generator differences.
3.  **Reproducibility:** Builds are deterministic across all environments.

## Updating Versions

If you update the version here, you MUST:
1.  Update `pyproject.toml`
2.  Update `.github/workflows/validate-proto.yml`
3.  Regenerate all proto files: `make proto`