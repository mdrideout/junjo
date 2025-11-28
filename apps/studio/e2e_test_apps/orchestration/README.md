# E2E Orchestration - Data Generation Layer

Orchestration layer for generating test data with multiple services and controlled concurrency.

## What It Does

1. **Generates random service names** using `coolname` (e.g., "brave-red-panda", "clever-blue-whale")
2. **Spawns multiple app instances** from Layer 1 (../app)
3. **Controls concurrency** to create realistic load patterns
4. **Tracks metadata** for verification in Layer 3

## Setup

```bash
cd e2e_test_apps/orchestration
uv sync
```

## Usage

### Mode 1: Cycle-Based (run N cycles)

Each cycle = all services run 1 workflow each.

```bash
uv run python generate_data.py \
  --num-services 3 \
  --num-cycles 10 \
  --concurrency 2
```

**What happens:**
- Creates 3 services with random names (e.g., "tree-car-fire", "happy-moon-star", "quick-blue-fox")
- Runs 10 cycles = each service runs 10 workflows = 30 total workflows
- 2 cycles run concurrently = 3 × 2 = 6 concurrent workflows
- Saves results to `test_run_metadata.json`

### Mode 2: Duration-Based (run for N seconds)

Runs cycles continuously until duration expires.

```bash
uv run python generate_data.py \
  --num-services 5 \
  --duration 30 \
  --concurrency 3
```

**What happens:**
- Creates 5 services
- Runs for 30 seconds
- As many cycles as possible in that time
- 3 cycles run concurrently = 5 × 3 = 15 concurrent workflows
- Good for sustained load testing

### Pollution Test (10 services, medium volume)

```bash
uv run python generate_data.py \
  --num-services 10 \
  --num-cycles 100 \
  --concurrency 5
```

**What this tests:**
- 10 services sending concurrently
- 1,000 total workflows (10 services × 100 cycles)
- 10 × 5 = 50 concurrent workflows
- High probability of mixed-service batches in backend
- Validates fix for cross-service contamination bug

### Stress Test (20 services, high volume)

```bash
uv run python generate_data.py \
  --num-services 20 \
  --num-cycles 500 \
  --concurrency 10
```

**What this tests:**
- 10,000 total workflows (20 services × 500 cycles)
- 20 × 10 = 200 concurrent workflows
- System stability under load
- Throughput measurements

### Load Test (duration-based)

```bash
uv run python generate_data.py \
  --num-services 15 \
  --duration 60 \
  --concurrency 5
```

**What this tests:**
- Sustained load for 60 seconds
- 15 × 5 = 75 concurrent workflows
- Real-world sustained traffic pattern

## Concurrency Model

```
Configuration:
  num_services = 10
  num_cycles = 100
  concurrency = 5

Execution:

Cycle 1: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ┐
Cycle 2: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ├─ asyncio.gather (5 cycles)
Cycle 3: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  │
Cycle 4: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  │
Cycle 5: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ┘

Cycle 6: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ┐
Cycle 7: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ├─ asyncio.gather (next 5)
...                                                  ┘

Total Concurrent Workflows: 10 services × 5 cycles = 50 workflows
Total Workflows: 10 services × 100 cycles = 1,000 workflows
```

## Output

**Console output (cycle-based):**
```
Generated 3 service names:
  1. brave-red-panda
  2. clever-blue-whale
  3. gentle-green-tree

Configuration:
  Services: 3
  Cycles: 10
  Concurrency: 2 cycles
  Total concurrent workflows: 6

Progress: 2/10 cycles completed
Progress: 4/10 cycles completed
...
Progress: 10/10 cycles completed

✅ Completed: 30 workflows in 1.23s
   Cycles completed: 10
   Workflows per service: 10
   Throughput: 24.39 workflows/sec
   Metadata saved to: test_run_metadata.json
```

**Console output (duration-based):**
```
Generated 3 service names:
  1. obedient-mosquito-of-chaos
  2. satisfied-quirky-waxbill
  3. outstanding-mamba-from-mars

Configuration:
  Services: 3
  Duration: 5 seconds
  Concurrency: 2 cycles
  Total concurrent workflows: 6

Running for 5 seconds...
Progress: 2 cycles completed (0.2s elapsed)
Progress: 4 cycles completed (0.5s elapsed)
...
Progress: 44 cycles completed (5.1s elapsed)

✅ Completed: 132 workflows in 5.08s
   Cycles completed: 44
   Workflows per service: 44
   Throughput: 25.99 workflows/sec
   Metadata saved to: test_run_metadata.json
```

**Metadata file (test_run_metadata.json):**
```json
{
  "config": {
    "num_services": 3,
    "num_cycles": 10,
    "duration_seconds": null,
    "concurrency": 2
  },
  "services": [
    "brave-red-panda",
    "clever-blue-whale",
    "gentle-green-tree"
  ],
  "results": {
    "total_workflows": 30,
    "cycles_completed": 10,
    "workflows_per_service": 10,
    "duration_seconds": 1.23,
    "throughput": 24.39
  }
}
```

## Parameters

**--num-services** (required)
- Number of unique services to create
- Each service gets a random 3-word name

**--num-cycles** (required if --duration not specified)
- Number of cycles to run
- Each cycle = all services run 1 workflow
- Total workflows = num_services × num_cycles

**--duration** (optional, overrides --num-cycles)
- Run for this many seconds
- Runs as many cycles as possible in the time limit
- Good for sustained load testing

**--concurrency** (optional, default: 5)
- Number of cycles to run concurrently
- Higher = more concurrent load on system
- Total concurrent workflows = num_services × concurrency

**--config** (optional, default: ../app/config.yaml)
- Path to config file for base app
- Must have valid API key configured

## Verification

After generating data, use Layer 3 (verification) to check results:

```bash
cd ../verification
uv run python verify_integrity.py    # Check for pollution
uv run python verify_completeness.py  # Check all data received
```

## Troubleshooting

**"config.yaml not found"**
- Make sure Layer 1 app has config.yaml: `ls ../app/config.yaml`
- Check --config path is correct

**Slow throughput**
- Reduce --concurrency to lower system load
- Check Junjo AI Studio logs: `docker compose logs`
- Monitor system resources

**Services not appearing in UI**
- Wait a few seconds for backend to process spans
- Check API key is valid in ../app/config.yaml
- Verify ingestion service is running
