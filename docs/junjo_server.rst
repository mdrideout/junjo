.. _junjo_server:

##############################################################
Junjo Server Intro
##############################################################

.. meta::
   :description: Debug and visualize Junjo AI workflows with Junjo Server's interactive telemetry platform. Step through LLM decisions, trace state changes, and understand agentic behavior.
   :keywords: junjo server, workflow debugging, AI observability, LLM tracing, state machine debugging, workflow visualization, opentelemetry

Junjo Server is a free, open-source telemetry visualization platform built specifically for debugging graph-based AI workflows. It ingests OpenTelemetry traces from your Junjo workflows and provides interactive tools to understand exactly what your LLMs are doing and why.

What is Junjo Server?
=====================

**Key Capabilities:**

- **Interactive Graph Exploration:** Click through your workflow's execution path
- **State Machine Step Debugging:** See every single state change, in order
- **LLM Decision Tracking:** Understand which conditions evaluated true/false
- **Trace Timeline:** Visualize concurrent execution and performance bottlenecks
- **Multi-Execution Comparison:** Compare different runs to identify issues

Why Use Junjo Server for AI Workflows?
=======================================

LLM-powered applications are inherently non-deterministic. Traditional debugging doesn't work well when:

- You need to understand why an LLM chose path A over path B
- State changes happen across multiple concurrent nodes
- You're testing complex agentic behaviors
- You need to verify eval-driven development results

Junjo Server solves this by providing **complete execution transparency**.

.. image:: _static/junjo-screenshot.png
   :alt: Junjo Server interactive workflow visualization
   :align: center
   :width: 800px

*Interactive workflow graph showing execution path and state changes*

Installation & Setup
====================

Junjo Server is composed of three Docker services that work together:

1. **Backend**: API server and data processing (SQLite + DuckDB)
2. **Ingestion Service**: High-throughput OpenTelemetry data receiver (BadgerDB)
3. **Frontend**: Web UI for visualization and debugging

Quick Start Options
-------------------

Option 1: Use the Bare-Bones Template (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The easiest way to get started is with the `Junjo Server Bare-Bones Template <https://github.com/mdrideout/junjo-server-bare-bones>`_, a GitHub template repository with a ready-to-use Docker Compose configuration:

.. code-block:: bash

    # Clone the template repository
    git clone https://github.com/mdrideout/junjo-server-bare-bones.git
    cd junjo-server-bare-bones

    # Configure environment
    cp .env.example .env
    # Edit .env with your settings

    # Start services
    docker compose up -d

    # Access UI
    open http://localhost:5153

This template provides a minimal, flexible foundation you can customize for your needs. See :doc:`deployment` for more details.

Option 2: Create Your Own Docker Compose File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you prefer to integrate Junjo Server into an existing project, here's a minimal Docker Compose example:

.. code-block:: yaml
    :caption: docker-compose.yml

    services:
      junjo-server-backend:
        image: mdrideout/junjo-server-backend:latest
        ports:
          - "1323:1323"   # HTTP API
          - "50053:50053" # Internal gRPC
        volumes:
          - ./.dbdata/sqlite:/dbdata/sqlite
          - ./.dbdata/duckdb:/dbdata/duckdb
        env_file: .env
        networks:
          - junjo-network

      junjo-server-ingestion:
        image: mdrideout/junjo-server-ingestion-service:latest
        ports:
          - "50051:50051" # OTel data ingestion (your app connects here)
          - "50052:50052" # Internal gRPC
        volumes:
          - ./.dbdata/badgerdb:/dbdata/badgerdb
        env_file: .env
        networks:
          - junjo-network

      junjo-server-frontend:
        image: mdrideout/junjo-server-frontend:latest
        ports:
          - "5153:80" # Web UI
        env_file: .env
        networks:
          - junjo-network
        depends_on:
          - junjo-server-backend
          - junjo-server-ingestion

    networks:
      junjo-network:
        driver: bridge

**Start the services:**

.. code-block:: bash

    # Create .env file (see Configuration section below)
    cp .env.example .env
    
    # Start all services
    docker compose up -d
    
    # Access the UI
    open http://localhost:5153

Resource Requirements
---------------------

Junjo Server is designed to run on minimal resources:

- **CPU**: Single shared vCPU is sufficient
- **RAM**: 1GB minimum
- **Storage**: Uses SQLite, DuckDB, and BadgerDB (all embedded databases)

This makes it affordable to deploy on small cloud VMs.

Configuration
=============

Step 1: Generate an API Key
----------------------------

1. Open Junjo Server UI at http://localhost:5153
2. Navigate to Settings → API Keys
3. Create a new API key
4. Copy the key to your environment

.. code-block:: bash

    export JUNJO_SERVER_API_KEY="your-api-key-here"

Step 2: Configure OpenTelemetry in Your Application
----------------------------------------------------

Install the required OpenTelemetry packages:

.. code-block:: bash

    pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc

Create an OpenTelemetry configuration file:

.. code-block:: python
    :caption: otel_config.py

    import os
    from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource

    def init_telemetry(service_name: str):
        """Configure OpenTelemetry for Junjo Server."""
        
        # Get API key from environment
        api_key = os.getenv("JUNJO_SERVER_API_KEY")
        if not api_key:
            raise ValueError("JUNJO_SERVER_API_KEY environment variable not set. "
                           "Generate a new API key in the Junjo Server UI.")
        
        # Create OpenTelemetry resource
        resource = Resource.create({"service.name": service_name})
        
        # Set up tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure Junjo Server exporter
        junjo_exporter = JunjoServerOtelExporter(
            host="localhost",  # Junjo Server ingestion service host
            port="50051",      # Port 50051 receives OpenTelemetry data
            api_key=api_key,
            insecure=True  # Use False in production with TLS
        )
        
        # Add span processor for tracing
        tracer_provider.add_span_processor(junjo_exporter.span_processor)
        trace.set_tracer_provider(tracer_provider)
        
        # (Optional) Set up metrics
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[junjo_exporter.metric_reader]
        )
        metrics.set_meter_provider(meter_provider)

Step 3: Initialize Telemetry in Your Application
-------------------------------------------------

Call the initialization function before executing workflows:

.. code-block:: python

    from otel_config import init_telemetry
    
    # Initialize telemetry
    init_telemetry(service_name="my-ai-workflow")
    
    # Execute your workflow - telemetry is automatic!
    await my_workflow.execute()

Key Features Deep Dive
======================

1. Interactive Graph Visualization
-----------------------------------

Click on any node in the execution graph to:

- See the exact state when that node executed
- View state patches applied by that node
- Drill down into subflows
- Explore concurrent execution branches

The graph shows the actual path taken during execution, making it easy to understand which conditions were met and which branches were followed.

.. image:: _static/junjo-screenshot.png
   :alt: Interactive workflow graph
   :align: center
   :width: 800px

2. State Step Debugging
------------------------

The state timeline shows every state update in chronological order:

- Which node made each change
- What the state looked like before/after
- JSON patch diffs for precise changes
- Filter by state fields

This is **critical** for understanding:

- Why certain conditions evaluated the way they did
- How data flows through your workflow
- Where unexpected state mutations occur
- LLM decision-making patterns

3. Trace Exploration
--------------------

Full OpenTelemetry trace view with:

- Span durations (find performance bottlenecks)
- Error tracking and stack traces
- LLM call details (when using OpenInference)
- Custom attributes from your code

4. Multi-Execution Comparison
------------------------------

Compare executions side-by-side:

- Same workflow with different inputs
- Before/after prompt changes
- Successful vs failed runs
- Different LLM models

Using with OpenInference for LLM Tracing
=========================================

Junjo Server automatically displays LLM-specific data when you instrument with OpenInference:

.. code-block:: bash

    # Install OpenInference instrumentation for your LLM provider
    pip install openinference-instrumentation-google-genai

.. code-block:: python

    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    
    # After setting up OpenTelemetry tracer provider
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

You'll see in Junjo Server:

- Full prompt text
- LLM responses
- Token usage
- Model parameters
- Latency metrics

Junjo-Specific Telemetry Attributes
====================================

Junjo automatically adds these attributes to OpenTelemetry spans:

Workflow Spans
--------------

- ``junjo.span_type``: "workflow" or "subflow"
- ``junjo.id``: Unique workflow instance ID
- ``junjo.workflow.state.start``: Initial state JSON
- ``junjo.workflow.state.end``: Final state JSON
- ``junjo.workflow.graph_structure``: Graph definition
- ``junjo.workflow.node.count``: Number of nodes executed
- ``junjo.workflow.store.id``: Store instance ID

Node Spans
----------

- ``junjo.span_type``: "node"
- ``junjo.id``: Unique node instance ID
- ``junjo.parent_id``: Parent workflow/subflow ID

Subflow Spans
-------------

- ``junjo.parent_id``: Parent workflow ID
- ``junjo.workflow.parent_store.id``: Parent store ID

These attributes power Junjo Server's specialized visualization and debugging features.

Complete Example
================

See working examples in the repository:

- `Base Example with Junjo Server <https://github.com/mdrideout/junjo/tree/main/examples/base>`_
- `AI Chat Example <https://github.com/mdrideout/junjo/tree/main/examples/ai_chat>`_

Using Other OpenTelemetry Platforms
====================================

**Important:** Junjo's telemetry works with **any** OpenTelemetry platform. The ``JunjoServerOtelExporter`` is specifically for Junjo Server, but all Junjo-specific span attributes are automatically included when you use standard OTLP exporters.

You can use Junjo Server alongside other platforms:

.. code-block:: python

    # Use both Junjo Server AND Jaeger
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    
    # Junjo Server
    junjo_exporter = JunjoServerOtelExporter(
        host="localhost",
        port="50051",
        api_key=api_key,
        insecure=True
    )
    tracer_provider.add_span_processor(junjo_exporter.span_processor)
    
    # Also send to Jaeger
    jaeger_exporter = OTLPSpanExporter(endpoint="http://jaeger:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

Platforms like Jaeger, Grafana, Honeycomb, etc. will receive all Junjo spans with their custom attributes, though they won't have Junjo Server's specialized workflow visualization.

Architecture Details
====================

Junjo Server uses a three-service architecture for scalability and reliability:

.. code-block:: text

    Your Application (Junjo Python Library)
           ↓ (sends OTel spans via gRPC)
    Ingestion Service :50051
           ↓ (writes to BadgerDB WAL)
           ↓ (backend polls via internal gRPC :50052)
    Backend Service :1323
           ↓ (stores in SQLite + DuckDB)
           ↓ (serves HTTP API)
    Frontend :5153
           (web UI)

**Port Reference:**

- **50051**: Public gRPC - Your application sends telemetry here
- **50052**: Internal gRPC - Backend reads from ingestion service
- **50053**: Internal gRPC - Backend server communication
- **1323**: Public HTTP - API server
- **5153**: Public HTTP - Web UI

Troubleshooting
===============

No data appearing in Junjo Server
----------------------------------

- Verify API key is set correctly: ``echo $JUNJO_SERVER_API_KEY``
- Check services are running: ``docker compose ps``
- Ensure ingestion service is accessible on port 50051
- Look for connection errors in your application logs
- Check ingestion service logs: ``docker compose logs junjo-server-ingestion``

Missing LLM data
----------------

- Install OpenInference instrumentors: ``pip install openinference-instrumentation-<provider>``
- Call ``.instrument()`` after setting up the tracer provider
- Verify the instrumentation is active in your application startup

Performance issues
------------------

- Use sampling for high-volume workflows
- The ingestion service uses BadgerDB as a write-ahead log for durability
- Backend polls and indexes data asynchronously
- See `Junjo Server repository <https://github.com/mdrideout/junjo-server>`_ for tuning options

Docker Compose not starting
----------------------------

- Ensure Docker network exists: ``docker network create junjo-network``
- Check environment variables are set in ``.env``
- View logs: ``docker compose logs``
- Try: ``docker compose down -v && docker compose up --build``

Next Steps
==========

- Explore :doc:`opentelemetry` for general OpenTelemetry configuration
- Learn about :doc:`visualizing_workflows` for static Graphviz diagrams
- See :doc:`eval_driven_dev` for testing workflows
- Review :doc:`concurrency` for understanding parallel execution traces