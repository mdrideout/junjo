# E2E Test Apps - Implementation Plan

> **Purpose:** End-to-end testing applications for Junjo AI Studio to validate system throughput, data integrity, and cross-service isolation under load.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Layer 1: Base Test Application](#layer-1-base-test-application)
- [Layer 2: Data Generation Orchestrator](#layer-2-data-generation-orchestrator)
- [Layer 3: Verification Scripts](#layer-3-verification-scripts)
- [Layer 4: K6 Load Testing](#layer-4-k6-load-testing)
- [Concurrency Model](#concurrency-model)
- [Setup Instructions](#setup-instructions)
- [Usage Examples](#usage-examples)
- [Testing Scenarios](#testing-scenarios)

---

## Overview

The E2E test apps provide a framework for:

1. **Pollution Testing** - Verify no cross-service data contamination when multiple services send telemetry concurrently
2. **Load Testing** - Measure system throughput and identify performance bottlenecks
3. **Integrity Testing** - Ensure all telemetry data is correctly received and indexed
4. **Stress Testing** - Validate system behavior under high concurrency

**Key Features:**
- Configurable number of services (uses random 3-word names like "tree-airplane-sausage")
- Controlled concurrency model (services × concurrent rounds)
- Based on Junjo getting_started example for realistic workflow patterns
- Automated verification of results
- K6 integration for professional load testing

---

## Architecture

### 4-Layer Design

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: K6 Load Testing                                    │
│ - gRPC load testing of ingestion endpoint                   │
│ - Performance metrics, percentiles, thresholds               │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Verification Scripts                               │
│ - Query backend API to verify results                       │
│ - Check data integrity (no pollution)                       │
│ - Check completeness (all data received)                    │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Data Generation Orchestrator                       │
│ - Generate random service names (coolname)                  │
│ - Spawn multiple app instances with controlled concurrency  │
│ - Track metadata for verification                           │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Base Test Application                              │
│ - Simple Junjo app with getting_started workflow            │
│ - Config file for OTLP endpoint, API key                    │
│ - Can run standalone or be orchestrated                     │
└─────────────────────────────────────────────────────────────┘
```

**Design Principles:**
- **Separation of concerns** - Each layer has one responsibility
- **Reusable components** - Base app can run standalone
- **Mix and match** - Use orchestrator for quick tests, K6 for load tests
- **CI/CD ready** - All layers scriptable and automatable

---

## Directory Structure

```
junjo-ai-studio/
├── e2e_test_apps/
│   │
│   ├── README.md                      # Overview, setup, usage
│   │
│   ├── 1_app/                         # Layer 1: Base test application
│   │   ├── pyproject.toml             # Dependencies: junjo
│   │   ├── uv.lock
│   │   ├── config.yaml.example        # OTLP config template
│   │   ├── main.py                    # Entry point (CLI + config support)
│   │   ├── workflows.py               # Workflow definitions (getting_started)
│   │   └── README.md                  # App-specific docs
│   │
│   ├── 2_orchestration/               # Layer 2: Data generation orchestrator
│   │   ├── pyproject.toml             # Dependencies: coolname
│   │   ├── generate_data.py           # CLI orchestrator
│   │   └── README.md                  # Usage docs
│   │
│   ├── 3_verification/                # Layer 3: Test assertions
│   │   ├── pyproject.toml             # Dependencies: requests
│   │   ├── verify_integrity.py        # Check for pollution
│   │   ├── verify_completeness.py     # Check all data received
│   │   └── README.md                  # Verification docs
│   │
│   ├── 4_load_testing/                # Layer 4: K6 load testing
│   │   ├── k6_scripts/
│   │   │   ├── ingestion_load.js      # gRPC load test
│   │   │   └── scenarios.js           # Ramp-up, sustained scenarios
│   │   ├── run_load_test.sh           # K6 runner script
│   │   └── README.md                  # K6 setup and usage
│   │
│   └── scripts/
│       ├── setup.sh                   # Install all dependencies
│       └── run_integrity_test.sh      # Generate data → Verify
│
└── E2E_TEST_PLAN.md                   # This document
```

---

## Layer 1: Base Test Application

### Purpose
A simple, standalone Junjo application that can be run individually or orchestrated by Layer 2.

### Files to Create

#### `1_app/config.yaml.example`

```yaml
# Junjo OTLP Exporter Configuration
exporter:
  api_key: "your_api_key_here"
  endpoint: "grpc://localhost:50051"
  service_name: "default-service"  # Overridden by CLI
  insecure: true  # Set false for production with TLS

# App Configuration
app:
  num_workflows: 1  # Default, overridden by CLI
  log_level: "INFO"
```

#### `1_app/main.py` (Minimal Example)

```python
"""Simple Junjo app based on getting_started example."""
import yaml
import argparse
from workflows import create_simple_workflow
from junjo import configure_exporter

def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--service-name", help="Override service name")
    parser.add_argument("--num-workflows", type=int, help="Override num workflows")
    args = parser.parse_args()

    config = load_config(args.config)
    service_name = args.service_name or config["exporter"]["service_name"]
    num_workflows = args.num_workflows or config["app"]["num_workflows"]

    # Configure exporter
    configure_exporter(
        endpoint=config["exporter"]["endpoint"],
        api_key=config["exporter"]["api_key"],
        service_name=service_name,
        insecure=config["exporter"]["insecure"],
    )

    # Run workflows
    for i in range(num_workflows):
        workflow = create_simple_workflow()
        await workflow.run(initial_state={"counter": 0, "iteration": i})

    print(f"[{service_name}] Completed {num_workflows} workflows")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

#### `1_app/workflows.py` (Minimal Example)

```python
"""Workflow definitions based on getting_started example."""
from junjo import Node, WorkflowBuilder

class IncrementNode(Node):
    async def execute(self, state):
        state.counter += 1
        return state

class DecrementNode(Node):
    async def execute(self, state):
        state.counter -= 1
        return state

def create_simple_workflow():
    """Create a simple workflow: Increment -> Decrement -> Increment."""
    return (WorkflowBuilder()
        .add_node(IncrementNode())
        .add_node(DecrementNode())
        .add_node(IncrementNode())
        .build())
```

#### `1_app/pyproject.toml`

```toml
[project]
name = "e2e-test-app"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "junjo",  # Or specify version/git URL
    "pyyaml",
]
```

**Standalone Usage:**
```bash
cd 1_app
cp config.yaml.example config.yaml
# Edit config.yaml with your API key

# Run single workflow
python main.py

# Run with overrides
python main.py --service-name "Service-Alpha" --num-workflows 10
```

---

## Layer 2: Data Generation Orchestrator

### Purpose
Generate test data by running multiple instances of the base app with controlled concurrency.

### Service Name Generation

Uses `coolname` library to generate unique 3-word service names:

```python
from coolname import generate_slug

# Generate 10 unique service names
services = [generate_slug(3) for _ in range(10)]
# Example output:
# ["brave-red-panda", "clever-blue-whale", "gentle-green-tree", ...]
```

### Files to Create

#### `2_orchestration/generate_data.py` (Minimal Example)

```python
"""CLI tool for generating test data with configurable concurrency."""
import argparse
import asyncio
import subprocess
from coolname import generate_slug
from pathlib import Path
import json
import time

async def run_workflow(service_name: str, workflow_num: int, config_path: str):
    """Run one workflow for a service."""
    process = await asyncio.create_subprocess_exec(
        "python", "../1_app/main.py",
        "--config", config_path,
        "--service-name", service_name,
        "--num-workflows", "1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()
    return service_name, workflow_num, process.returncode

async def execute_round(services: list[str], round_num: int, config_path: str):
    """Execute one round: all services run 1 workflow each (concurrent)."""
    tasks = [run_workflow(service, round_num, config_path) for service in services]
    results = await asyncio.gather(*tasks)  # All services run together
    return round_num, results

async def generate_data(num_services, workflows_per_service, concurrency, config_path):
    """
    Generate test data with controlled concurrency.

    Execution model:
        - Round = all services execute 1 workflow each (asyncio.gather)
        - Concurrency = number of rounds running simultaneously
        - Total concurrent workflows = num_services × concurrency
    """
    # Generate unique service names
    services = [generate_slug(3) for _ in range(num_services)]

    print(f"Generated {num_services} service names")
    print(f"Total concurrent workflows: {num_services * concurrency}")

    start = time.time()

    # Create all rounds
    rounds = []
    for round_num in range(workflows_per_service):
        rounds.append(execute_round(services, round_num, config_path))

    # Execute rounds with concurrency limit
    for i in range(0, len(rounds), concurrency):
        batch = rounds[i:i+concurrency]
        await asyncio.gather(*batch)  # Multiple rounds execute together

    duration = time.time() - start
    total = num_services * workflows_per_service

    # Save metadata for verification
    metadata = {
        "config": {
            "num_services": num_services,
            "workflows_per_service": workflows_per_service,
            "concurrency": concurrency,
        },
        "services": services,
        "results": {
            "total_workflows": total,
            "duration_seconds": duration,
            "throughput": total / duration,
        }
    }

    with open("test_run_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"✅ Completed: {total} workflows in {duration:.2f}s")
    return metadata

def main():
    parser = argparse.ArgumentParser(description="Generate test data")
    parser.add_argument("--num-services", type=int, required=True)
    parser.add_argument("--workflows-per-service", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--config", default="../1_app/config.yaml")
    args = parser.parse_args()

    asyncio.run(generate_data(
        args.num_services,
        args.workflows_per_service,
        args.concurrency,
        args.config,
    ))

if __name__ == "__main__":
    main()
```

#### `2_orchestration/pyproject.toml`

```toml
[project]
name = "e2e-orchestration"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "coolname",
]
```

---

## Layer 3: Verification Scripts

### Purpose
Query the backend API to verify test results and check for data integrity issues.

### Files to Create

#### `3_verification/verify_integrity.py` (Minimal Example)

```python
"""Verify no cross-service contamination."""
import json
import requests
import sys
import time

def verify_integrity():
    # Wait for backend to process spans
    print("Waiting 5 seconds for backend processing...")
    time.sleep(5)

    # Load metadata from orchestrator
    with open("../2_orchestration/test_run_metadata.json") as f:
        metadata = json.load(f)

    services = metadata["services"]
    expected_workflows = metadata["config"]["workflows_per_service"]

    print(f"Verifying integrity for {len(services)} services...")

    failures = []
    for service in services:
        # Query workflows for this service
        response = requests.get(
            f"http://localhost:1323/api/v1/observability/services/{service}/workflows"
        )
        workflows = response.json()

        # Check count
        if len(workflows) != expected_workflows:
            failures.append(
                f"{service}: Expected {expected_workflows}, got {len(workflows)}"
            )

        # Check for pollution
        for wf in workflows:
            if wf["service_name"] != service:
                failures.append(
                    f"{service}: Found workflow with service_name={wf['service_name']} (POLLUTION!)"
                )

    if failures:
        print("\n❌ Integrity check FAILED:")
        for failure in failures:
            print(f"  {failure}")
        sys.exit(1)
    else:
        print(f"✅ Integrity check PASSED")
        print(f"   All {len(services)} services have correct data separation")
        sys.exit(0)

if __name__ == "__main__":
    verify_integrity()
```

#### `3_verification/verify_completeness.py` (Minimal Example)

```python
"""Verify all expected data was received."""
import json
import requests
import sys
import time

def verify_completeness():
    time.sleep(5)  # Wait for processing

    with open("../2_orchestration/test_run_metadata.json") as f:
        metadata = json.load(f)

    services = metadata["services"]
    expected_total = metadata["results"]["total_workflows"]

    # Query total workflows across all services
    total_received = 0
    for service in services:
        response = requests.get(
            f"http://localhost:1323/api/v1/observability/services/{service}/workflows"
        )
        total_received += len(response.json())

    if total_received != expected_total:
        print(f"❌ Completeness check FAILED")
        print(f"   Expected: {expected_total} workflows")
        print(f"   Received: {total_received} workflows")
        print(f"   Missing: {expected_total - total_received}")
        sys.exit(1)
    else:
        print(f"✅ Completeness check PASSED")
        print(f"   All {expected_total} workflows received")
        sys.exit(0)

if __name__ == "__main__":
    verify_completeness()
```

#### `3_verification/pyproject.toml`

```toml
[project]
name = "e2e-verification"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "requests",
]
```

---

## Layer 4: K6 Load Testing

### Purpose
Professional load testing of the ingestion endpoint using K6.

### Why K6?
- ✅ Native gRPC support
- ✅ Built-in metrics (percentiles, trends)
- ✅ Industry-standard load testing tool
- ✅ Better for performance testing than Locust

### Files to Create

#### `4_load_testing/k6_scripts/ingestion_load.js` (Minimal Example)

```javascript
import grpc from 'k6/net/grpc';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    sustained_load: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
    },
  },
  thresholds: {
    'grpc_req_duration': ['p(95)<500'],  // 95% under 500ms
    'grpc_req_failed': ['rate<0.01'],    // < 1% errors
  },
};

const client = new grpc.Client();
client.load(['../../../proto'], 'trace_service.proto');

export default function () {
  client.connect('localhost:50051', {
    plaintext: true,
    metadata: {
      'x-junjo-api-key': __ENV.JUNJO_API_KEY,
    },
  });

  // Send OTLP span (payload would be defined here)
  const response = client.invoke('TraceService/Export', {});

  check(response, {
    'status is OK': (r) => r && r.status === grpc.StatusOK,
  });

  client.close();
  sleep(0.1);
}
```

#### `4_load_testing/run_load_test.sh`

```bash
#!/bin/bash
set -e

echo "Starting K6 load test..."

k6 run \
  --out json=results/$(date +%Y%m%d_%H%M%S).json \
  --env JUNJO_API_KEY="$JUNJO_API_KEY" \
  k6_scripts/ingestion_load.js

echo "Load test complete! Check results/ directory"
```

**Usage:**
```bash
cd 4_load_testing

# Run K6 test
export JUNJO_API_KEY="your_key_here"
./run_load_test.sh

# Or run directly
k6 run k6_scripts/ingestion_load.js
```

---

## Concurrency Model

### Visual Explanation

```
Configuration:
  num_services = 10
  workflows_per_service = 100
  concurrency = 5

Execution Model:

Round 1: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ─┐
Round 2: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]   │
Round 3: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]   ├─ asyncio.gather (5 rounds)
Round 4: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]   │
Round 5: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ─┘

Round 6: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]  ─┐
Round 7: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]   ├─ asyncio.gather (next 5 rounds)
...                                                   │
Round 10: [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10] ─┘

... (continues until 100 rounds complete)

Total Concurrent Workflows: 10 services × 5 rounds = 50 workflows
Total Workflows: 10 services × 100 rounds = 1,000 workflows
```

### Implementation

```python
# Round execution
async def execute_round(services, round_num, config_path):
    """All services execute 1 workflow each."""
    tasks = [run_workflow(service, round_num, config_path) for service in services]
    await asyncio.gather(*tasks)  # All services run together

# Concurrency control
rounds = [execute_round(services, i, config) for i in range(workflows_per_service)]

for i in range(0, len(rounds), concurrency):
    batch = rounds[i:i+concurrency]
    await asyncio.gather(*batch)  # Multiple rounds run together
```

### Why This Model?

1. **Realistic pollution testing** - Multiple services sending spans simultaneously
2. **Controlled load** - Predictable concurrent workflow count
3. **Scalable** - Easy to adjust parameters
4. **Measurable** - Clear throughput metrics

---

## Setup Instructions

### 1. Install Dependencies

```bash
cd e2e_test_apps

# Layer 1: Base app
cd 1_app
uv sync
cp config.yaml.example config.yaml
# Edit config.yaml with your API key

# Layer 2: Orchestrator
cd ../2_orchestration
uv sync

# Layer 3: Verification
cd ../3_verification
uv sync

# Layer 4: K6 (install K6 separately)
brew install k6  # macOS
# or: https://k6.io/docs/getting-started/installation/
```

### 2. Configure Base App

Edit `1_app/config.yaml`:

```yaml
exporter:
  api_key: "your_actual_api_key_from_junjo_ai_studio"
  endpoint: "grpc://localhost:50051"
  service_name: "default-service"
  insecure: true
```

### 3. Start Junjo AI Studio

```bash
# In main project directory
docker compose up -d

# Verify services running
docker compose ps
```

---

## Usage Examples

### Quick Test (3 services, low volume)

```bash
cd e2e_test_apps/2_orchestration

# Generate data
python generate_data.py \
  --num-services 3 \
  --workflows-per-service 10 \
  --concurrency 2

# Verify
cd ../3_verification
python verify_integrity.py
python verify_completeness.py
```

**Expected Result:**
- 3 services with random names
- 10 workflows per service = 30 total
- 3 × 2 = 6 concurrent workflows
- All data correctly separated

### Pollution Test (10 services, medium volume)

```bash
cd e2e_test_apps/2_orchestration

python generate_data.py \
  --num-services 10 \
  --workflows-per-service 100 \
  --concurrency 5

cd ../3_verification
python verify_integrity.py
```

**What This Tests:**
- 10 services sending concurrently
- 1,000 total workflows
- 10 × 5 = 50 concurrent workflows
- High probability of mixed-service batches in backend
- Validates fix for cross-service contamination bug

### Stress Test (20 services, high volume)

```bash
cd e2e_test_apps/2_orchestration

python generate_data.py \
  --num-services 20 \
  --workflows-per-service 500 \
  --concurrency 10

cd ../3_verification
python verify_integrity.py
python verify_completeness.py
```

**What This Tests:**
- 10,000 total workflows
- 20 × 10 = 200 concurrent workflows
- System stability under load
- Throughput measurements

---

## Testing Scenarios

### 1. Integrity Test (Cross-Service Pollution)

**Goal:** Verify no cross-service contamination

**Setup:**
```bash
python generate_data.py --num-services 5 --workflows-per-service 50 --concurrency 5
```

**Verification:**
- Each service should have exactly 50 workflows
- Each workflow's `service_name` should match its service
- No "leakage" between services

**Pass Criteria:**
- ✅ All services have correct workflow count
- ✅ All workflows have correct `service_name`
- ✅ No pollution detected

### 2. Throughput Test

**Goal:** Measure system capacity

**Setup:**
```bash
python generate_data.py --num-services 10 --workflows-per-service 1000 --concurrency 10
```

**Metrics:**
- Total workflows: 10,000
- Concurrent workflows: 100
- Throughput: workflows/sec
- Duration: total time to complete

**Pass Criteria:**
- ✅ Acceptable throughput (e.g., > 100 workflows/sec)
- ✅ All data received (completeness check)
- ✅ No errors during execution

### 3. Load Test (K6)

**Goal:** Test ingestion endpoint performance

**Setup:**
```bash
cd e2e_test_apps/4_load_testing
export JUNJO_API_KEY="your_key"
k6 run k6_scripts/ingestion_load.js
```

**Metrics:**
- Requests/sec
- p95, p99 latency
- Error rate

**Pass Criteria:**
- ✅ p95 < 500ms
- ✅ Error rate < 1%
- ✅ System remains stable

---

## Helper Scripts

### `scripts/setup.sh`

```bash
#!/bin/bash
set -e

echo "Setting up E2E test apps..."

# Install dependencies for each layer
for layer in 1_app 2_orchestration 3_verification; do
    echo "Installing $layer dependencies..."
    cd $layer
    uv sync
    cd ..
done

# Copy config template
if [ ! -f 1_app/config.yaml ]; then
    cp 1_app/config.yaml.example 1_app/config.yaml
    echo "Created 1_app/config.yaml - please edit with your API key"
fi

echo "✅ Setup complete!"
echo "Next steps:"
echo "  1. Edit 1_app/config.yaml with your API key"
echo "  2. Run: cd 2_orchestration && python generate_data.py --help"
```

### `scripts/run_integrity_test.sh`

```bash
#!/bin/bash
set -e

echo "Running integrity test..."

# Generate data
cd 2_orchestration
python generate_data.py \
  --num-services 5 \
  --workflows-per-service 100 \
  --concurrency 5

# Wait for processing
echo "Waiting for backend processing..."
sleep 5

# Verify
cd ../3_verification
python verify_integrity.py
python verify_completeness.py

echo "✅ Integrity test complete!"
```

---

## Future Enhancements

1. **K6 Integration**
   - xk6-exec extension to run base app from K6
   - Custom metrics for workflow execution time
   - Grafana dashboard integration

2. **Additional Scenarios**
   - Burst load (sudden spike in traffic)
   - Gradual ramp-up (slowly increasing load)
   - Sustained load with failures (chaos testing)

3. **Enhanced Verification**
   - Check workflow graph structure integrity
   - Verify state transitions
   - Check timestamp ordering

4. **CI/CD Integration**
   - GitHub Actions workflow for E2E tests
   - Automated regression testing
   - Performance benchmarking over time

---

## Troubleshooting

### Data Not Appearing in Backend

**Check:**
1. Config file has correct API key: `cat 1_app/config.yaml`
2. Ingestion service is running: `docker compose ps junjo-ai-studio-ingestion`
3. Check ingestion logs: `docker compose logs junjo-ai-studio-ingestion`
4. Trigger a flush: Data appears after `FlushWAL` (cold tier) or `PrepareHotSnapshot` (hot tier)
5. Check Parquet files exist: `ls -la .dbdata/spans/parquet/`

### Pollution Detected

**This means the bug we fixed has regressed!**

1. Check `test_run_metadata.json` for service names
2. Query backend API manually for each service
3. Look for workflows with mismatched `service_name`
4. Review backend span processing logic

### Low Throughput

**Bottlenecks to check:**
1. Ingestion endpoint (check K6 metrics)
2. WAL flush frequency (FlushWAL creates cold Parquet files)
3. Hot snapshot generation (PrepareHotSnapshot for real-time queries)
4. DataFusion query performance (check Parquet file sizes)
5. Network (local vs Docker network)

---

## Summary

This E2E testing framework provides:

✅ **Configurable test generation** - Control scale and concurrency
✅ **Realistic scenarios** - Based on actual Junjo workflows
✅ **Automated verification** - Detect pollution and data loss
✅ **Professional load testing** - K6 integration
✅ **CI/CD ready** - Scriptable and automatable

**Next Steps:**
1. Implement Layer 1 (base app)
2. Implement Layer 2 (orchestrator)
3. Implement Layer 3 (verification)
4. Run pollution test to validate the fix
5. Implement Layer 4 (K6) for load testing
