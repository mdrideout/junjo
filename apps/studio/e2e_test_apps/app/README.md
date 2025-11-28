# E2E Test App - Base Test Application

Simple Junjo application for E2E testing of Junjo AI Studio. Based on the getting_started example with full workflow complexity (Graph, Edges, Conditions, branching logic).

## Setup

1. **Install dependencies:**
   ```bash
   cd e2e_test_apps/app
   uv sync
   ```

2. **Create configuration file:**
   ```bash
   cp config.yaml.example config.yaml
   ```

3. **Edit `config.yaml` with your API key:**
   ```yaml
   exporter:
     api_key: "your_actual_api_key_here"  # Get from Junjo AI Studio Settings → API Keys
     endpoint: "grpc://localhost:50051"
     service_name: "default-service"
     insecure: true

   app:
     num_workflows: 1
     log_level: "INFO"
   ```

## Usage

### Run with defaults

```bash
uv run python main.py
```

Uses `config.yaml` settings, runs 1 workflow with service name "default-service".

### Run with custom service name

```bash
uv run python main.py --service-name "my-test-service"
```

### Run multiple workflows

```bash
uv run python main.py --num-workflows 10
```

Runs 10 workflows, varying the items list for each execution.

### Run with all overrides

```bash
uv run python main.py \
  --config config.yaml \
  --service-name "Service-Alpha" \
  --num-workflows 100
```

## Workflow Details

The test app uses the getting_started workflow structure:

**Nodes:**
1. `FirstNode` - Entry point
2. `CountItemsNode` - Counts items in state
3. `EvenItemsNode` or `OddItemsNode` - Branching based on count
4. `FinalNode` - Exit point

**State:**
- `items: list[str]` - List of items (varies per workflow)
- `count: int | None` - Count of items (computed by CountItemsNode)

**Branching Logic:**
- If count is even → `EvenItemsNode`
- If count is odd → `OddItemsNode`

## Verification

After running, verify telemetry in Junjo AI Studio:

1. Open Junjo AI Studio web UI (http://localhost:5153)
2. Navigate to the service you specified
3. Check that workflows appear with correct service name
4. Inspect workflow graph structure and state transitions

## Use Cases

**Standalone testing:**
```bash
# Test single workflow
uv run python main.py --service-name "test-service"
```

**Orchestrated testing:**
- Used by Layer 2 (orchestration) to generate test data
- Spawned multiple times with different service names
- Creates realistic multi-service telemetry data

## Troubleshooting

**"Connection refused" error:**
- Ensure Junjo AI Studio is running: `docker compose ps`
- Check ingestion service is up: `docker compose logs junjo-ai-studio-ingestion`

**No data appearing in UI:**
- Verify API key is correct in `config.yaml`
- Check backend logs: `docker compose logs junjo-ai-studio-backend`
- Wait a few seconds for backend to process spans

**Import errors:**
- Run `uv sync` to install dependencies
- Check Python version: `python --version` (requires >= 3.13)
