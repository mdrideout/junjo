# Protocol Buffer Tool Versions

This document specifies the **locked versions** of Protocol Buffer tools used across the Junjo AI Studio project. All environments (local development, CI/CD, Docker builds) must use these exact versions to ensure generated code is identical.

## Required Tool Versions

| Tool | Version | Purpose |
|------|---------|---------|
| **protoc** | v30.2 | Protocol Buffer compiler |
| **protoc-gen-go** | v1.36.10 | Go code generator for protobuf messages |
| **protoc-gen-go-grpc** | v1.5.1 | Go code generator for gRPC services |
| **grpcio-tools** | 1.76.0 | Python protobuf/gRPC code generator |

## Why Lock Versions?

Different versions of `protoc` and its plugins generate **structurally different code**:
- protoc v29/v30: Uses string concatenation (`const ... = "" + "\n" + ...`)
- protoc v3.x: Uses byte arrays (`var ... = string([]byte{...})`)

Even though the generated code is functionally equivalent, `git diff` detects these differences, causing CI validation to fail.

**By locking to v30.2 everywhere**, we ensure:
✅ Identical code generation across all environments
✅ CI validation passes without false positives
✅ No surprises from package manager version updates
✅ Reproducible builds

## Installation Instructions

### macOS

**Install protoc v30.2:**
```bash
PROTOC_VERSION=30.2
curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-osx-x86_64.zip
sudo unzip -o protoc-${PROTOC_VERSION}-osx-x86_64.zip -d /usr/local bin/protoc
sudo unzip -o protoc-${PROTOC_VERSION}-osx-x86_64.zip -d /usr/local 'include/*'
rm protoc-${PROTOC_VERSION}-osx-x86_64.zip
```

**Install Go plugins:**
```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
```

**Install Python tools (via uv):**
```bash
cd backend
uv sync  # Installs grpcio-tools==1.76.0 from uv.lock
```

### Linux

**Install protoc v30.2:**
```bash
PROTOC_VERSION=30.2
curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-x86_64.zip
sudo unzip -o protoc-${PROTOC_VERSION}-linux-x86_64.zip -d /usr/local bin/protoc
sudo unzip -o protoc-${PROTOC_VERSION}-linux-x86_64.zip -d /usr/local 'include/*'
rm protoc-${PROTOC_VERSION}-linux-x86_64.zip
```

**Install Go plugins:**
```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
```

**Install Python tools (via uv):**
```bash
cd backend
uv sync  # Installs grpcio-tools==1.76.0 from uv.lock
```

### Windows

**Install protoc v30.2:**
```powershell
$PROTOC_VERSION = "30.2"
Invoke-WebRequest -Uri "https://github.com/protocolbuffers/protobuf/releases/download/v$PROTOC_VERSION/protoc-$PROTOC_VERSION-win64.zip" -OutFile "protoc.zip"
Expand-Archive -Path protoc.zip -DestinationPath "C:\protoc" -Force
# Add C:\protoc\bin to your PATH
Remove-Item protoc.zip
```

**Install Go plugins:**
```powershell
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
```

**Install Python tools (via uv):**
```powershell
cd backend
uv sync  # Installs grpcio-tools==1.76.0 from uv.lock
```

## Verification

After installation, verify versions:

```bash
protoc --version
# Expected: libprotoc 30.2

protoc-gen-go --version
# Expected: protoc-gen-go v1.36.10

protoc-gen-go-grpc --version
# Expected: protoc-gen-go-grpc 1.5.1

# For Python (from backend directory with uv environment active)
uv run python -m grpc_tools.protoc --version
# Expected: libprotoc 30.2 (bundled with grpcio-tools)
```

### Quick Validation Script

Run this one-liner to check all versions at once:

```bash
echo "protoc: $(protoc --version 2>&1 | awk '{print $2}')" && \
echo "protoc-gen-go: $(protoc-gen-go --version 2>&1 | awk '{print $2}')" && \
echo "protoc-gen-go-grpc: $(protoc-gen-go-grpc --version 2>&1 | awk '{print $2}')"
```

Expected output:
```
protoc: 30.2
protoc-gen-go: v1.36.10
protoc-gen-go-grpc: 1.5.1
```

### Pre-commit Hook Validation

The pre-commit hook (`scripts/pre-commit.sh`) **automatically checks versions** before generating proto files. If version mismatches are detected, you'll see warnings like:

```
⚠️  Warning: protoc version mismatch
     Expected: v30.2
     Found:    v29.3

📚 To install correct versions, see: PROTO_VERSIONS.md
```

**Note**: The hook will continue with generation even if versions don't match (to avoid blocking commits), but **you should update your tools** to ensure consistency with CI/CD and other developers.

## Regenerating Proto Files

### Go (ingestion)
```bash
cd ingestion
make proto
```

### Python (backend)
```bash
cd backend
./scripts/generate_proto.sh
```

### Automated via Pre-commit Hook
Install the pre-commit hook to automatically regenerate proto files before each commit:
```bash
./scripts/install-git-hooks.sh
```

The hook will:
- Regenerate proto files for both Go and Python
- Stage updated files automatically
- Prevent commits with stale proto code

## CI/CD Integration

All environments use identical versions:

- **GitHub Actions** (`.github/workflows/validate-proto.yml`): Downloads protoc v30.2 binary
- **Docker Development** (`*/Dockerfile` development stages): Downloads protoc v30.2 binary
- **Docker Production** (`*/Dockerfile` builder stages): Downloads protoc v30.2 binary

The validate-proto workflow ensures proto files are never out of sync by:
1. Regenerating all proto files from scratch
2. Running `git diff` to check for changes
3. Failing the build if any differences are detected

## Troubleshooting

### Pre-commit hook shows version warnings
**Symptom**: You see warnings during commit about version mismatches

**Solution**:
1. Check your current versions:
   ```bash
   protoc --version
   protoc-gen-go --version
   protoc-gen-go-grpc --version
   ```

2. If using Homebrew's protoc, **remove it**:
   ```bash
   brew uninstall protobuf
   ```

3. Install the correct versions following the [Installation Instructions](#installation-instructions) above

4. Verify your shell uses the correct protoc:
   ```bash
   which protoc  # Should show ~/.local/bin/protoc or similar, NOT /usr/local/bin or /opt/homebrew/bin
   ```

5. If PATH is incorrect, ensure `~/.local/bin` comes first:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   # Add to ~/.zshrc or ~/.bashrc to make permanent
   ```

### "protoc: command not found"
- Ensure protoc is in your PATH
- Verify installation with `which protoc`

### "protoc-gen-go: program not found"
- Ensure `$GOPATH/bin` is in your PATH
- On macOS/Linux: `export PATH="$PATH:$(go env GOPATH)/bin"`
- Verify with `which protoc-gen-go`

### Generated code differs from committed files
- Ensure you have the correct versions installed (see Verification above)
- Regenerate proto files with the commands above
- If using Homebrew's protoc, uninstall it: `brew uninstall protobuf`

### CI validation fails with "Proto files are out of date"
- Your local protoc version differs from v30.2
- Install v30.2 manually (do not use package managers)
- Regenerate proto files locally
- Commit the updated files

## Version Update Process

When updating to newer tool versions:

1. Update version numbers in this file
2. Update `.github/workflows/validate-proto.yml`
3. Update all Dockerfiles (`ingestion/Dockerfile`, `backend/Dockerfile`)
4. Regenerate proto files locally
5. Test Docker builds for all services
6. Commit all updated files in a single commit
7. Notify all developers to update their local installations

## References

- [Protocol Buffers Official Site](https://protobuf.dev/)
- [protoc Releases](https://github.com/protocolbuffers/protobuf/releases)
- [protoc-gen-go Releases](https://github.com/protocolbuffers/protobuf-go/releases)
- [protoc-gen-go-grpc](https://pkg.go.dev/google.golang.org/grpc/cmd/protoc-gen-go-grpc)
- [grpcio-tools PyPI](https://pypi.org/project/grpcio-tools/)
