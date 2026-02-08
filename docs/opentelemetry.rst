.. _opentelemetry:

##############################################################
OpenTelemetry Integration
##############################################################

.. meta::
   :description: Junjo provides automatic OpenTelemetry instrumentation for AI workflows. Learn how it works and how to configure exporters for any observability platform.
   :keywords: junjo, opentelemetry, tracing, observability, OTLP, jaeger, grafana, honeycomb

Junjo automatically instruments your workflows with OpenTelemetry spans. Every workflow and node execution is traced without any code changes to your workflow logic.

How Junjo Uses OpenTelemetry
=============================

**What Gets Traced Automatically:**

- Workflow execution (start state, end state, graph structure)
- Individual node execution
- Subflow execution with parent relationships
- RunConcurrent parallel execution
- State machine updates

**No Manual Instrumentation Required:**

Once you configure an OpenTelemetry exporter, Junjo handles the rest. Your workflow code stays clean and focused on business logic.

.. code-block:: python

    # Your workflow code stays the same
    await my_workflow.execute()
    
    # Junjo automatically creates spans with rich attributes

Automatic Span Creation
========================

When you execute a workflow, Junjo creates a hierarchy of OpenTelemetry spans:

.. code-block:: text

    Workflow Span
    ├── Node Span (source)
    ├── Node Span
    ├── Subflow Span
    │   ├── Node Span
    │   └── Node Span
    └── Node Span (sink)

Each span includes Junjo-specific attributes that provide workflow context.

Choosing an OpenTelemetry Exporter
===================================

Junjo works with any OpenTelemetry-compatible platform. Choose based on your needs:

1. Junjo AI Studio (Recommended for AI Workflows)
--------------------------------------------------

Built specifically for graph workflow debugging with:

- Interactive state stepping
- Workflow-specific visualization
- LLM decision tracking

See :doc:`junjo_ai_studio` for complete setup.

.. code-block:: python

    from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
    
    junjo_exporter = JunjoOtelExporter(
        host="localhost",  # Junjo AI Studio ingestion service
        port="50051",      # gRPC port for receiving spans
        api_key=api_key,
        insecure=True      # Use False in production with TLS
    )
    tracer_provider.add_span_processor(junjo_exporter.span_processor)

2. Jaeger
---------

General-purpose distributed tracing, good for microservices integration.

.. code-block:: python

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    
    jaeger_exporter = OTLPSpanExporter(
        endpoint="http://jaeger:4317",
        insecure=True
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

3. Grafana/Tempo
----------------

Metrics + traces in one platform, good for production monitoring.

.. code-block:: python

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    
    tempo_exporter = OTLPSpanExporter(
        endpoint="http://tempo:4318/v1/traces",
        headers={"Authorization": "Bearer <token>"}
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(tempo_exporter))

4. Honeycomb, Datadog, New Relic, etc.
---------------------------------------

Enterprise observability platforms with full-featured APM.

.. code-block:: python

    # Example: Honeycomb
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    
    honeycomb_exporter = OTLPSpanExporter(
        endpoint="https://api.honeycomb.io/v1/traces",
        headers={"x-honeycomb-team": "<api-key>"}
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(honeycomb_exporter))

Using Multiple Exporters
=========================

You can send telemetry to multiple platforms simultaneously:

.. code-block:: python

    from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry import trace
    
    # Create resource
    resource = Resource.create({"service.name": "my-workflow"})
    
    # Set up tracer provider
    tracer_provider = TracerProvider(resource=resource)
    
    # Add Junjo AI Studio exporter
    junjo_exporter = JunjoOtelExporter(
        host="localhost",  # Junjo AI Studio ingestion service
        port="50051",      # gRPC port for receiving spans
        api_key=junjo_api_key,
        insecure=True      # Use False in production with TLS
    )
    tracer_provider.add_span_processor(junjo_exporter.span_processor)
    
    # Also send to Jaeger
    jaeger_exporter = OTLPSpanExporter(endpoint="http://jaeger:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    
    # Set as global tracer provider
    trace.set_tracer_provider(tracer_provider)

Junjo's Custom Span Attributes
===============================

Junjo adds workflow-specific attributes to all spans. These work with any OTLP exporter:

Workflow/Subflow Span Attributes
---------------------------------

.. code-block:: python

    {
        "junjo.span_type": "workflow" | "subflow",
        "junjo.id": "<unique-workflow-id>",
        "junjo.workflow.state.start": "<initial-state-json>",
        "junjo.workflow.state.end": "<final-state-json>",
        "junjo.workflow.graph_structure": "<graph-definition-json>",
        "junjo.workflow.node.count": 5,
        "junjo.workflow.store.id": "<store-id>",
        
        # Subflow only:
        "junjo.parent_id": "<parent-workflow-id>",
        "junjo.workflow.parent_store.id": "<parent-store-id>"
    }

Node Span Attributes
--------------------

.. code-block:: python

    {
        "junjo.span_type": "node",
        "junjo.id": "<unique-node-id>",
        "junjo.parent_id": "<parent-workflow-id>"
    }

These attributes enable:

- Filtering spans by workflow or node type
- Correlating nodes with their parent workflows
- Viewing state changes over time
- Understanding graph structure

Complete Configuration Example
===============================

Here's a complete OpenTelemetry setup for Junjo:

.. code-block:: python
    :caption: otel_config.py

    import os
    from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    
    def init_telemetry(service_name: str):
        """Configure OpenTelemetry with Junjo AI Studio."""
        
        # Get API key and determine environment
        api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
        if not api_key:
            raise ValueError("JUNJO_AI_STUDIO_API_KEY environment variable not set")
        
        is_production = os.getenv("ENV", "development") == "production"
        
        # Create resource
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("ENV", "development")
        })
        
        # Set up tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure Junjo AI Studio exporter
        junjo_exporter = JunjoOtelExporter(
            host="localhost",  # Junjo AI Studio ingestion service
            port="50051",      # gRPC port for receiving spans
            api_key=api_key,
            insecure=not is_production  # True for local dev, False for production
        )
        
        # Add span processor
        tracer_provider.add_span_processor(junjo_exporter.span_processor)
        
        # Set as global tracer provider
        trace.set_tracer_provider(tracer_provider)
        
        print(f"OpenTelemetry configured for {service_name}")
        print(f"Sending traces to Junjo AI Studio at localhost:50051")

Use in your application:

.. code-block:: python

    from otel_config import init_telemetry
    
    # Initialize before running workflows
    init_telemetry(service_name="my-ai-workflow")
    
    # Execute workflows - automatic instrumentation
    await my_workflow.execute()

Advanced Configuration
======================

Sampling
--------

Reduce telemetry volume with sampling:

.. code-block:: python

    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    
    # Sample 10% of traces
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(0.1)
    )

Custom Resource Attributes
---------------------------

Add custom attributes to all spans:

.. code-block:: python

    resource = Resource.create({
        "service.name": "my-workflow",
        "service.version": "2.0.0",
        "deployment.environment": "production",
        "team.name": "ai-team",
        "custom.attribute": "value"
    })

Context Propagation
-------------------

Propagate trace context across services:

.. code-block:: python

    from opentelemetry import propagate
    from opentelemetry.propagators.b3 import B3MultiFormat
    
    # Use B3 propagation format
    propagate.set_global_textmap(B3MultiFormat())

What You See in Your Platform
==============================

When viewing Junjo traces in your observability platform, you'll see:

**Span Hierarchy:**

- Clear parent-child relationships between workflows and nodes
- Nested subflows with their internal nodes
- Concurrent execution timing (RunConcurrent)

**Custom Attributes:**

- All ``junjo.*`` attributes for filtering and analysis
- State snapshots at workflow start/end
- Graph structure for understanding workflow design

**Performance Metrics:**

- Node execution duration
- Workflow total duration
- Concurrent execution overlap

**Platforms without Junjo AI Studio** will receive all this data but display it in their standard trace viewer. **Junjo AI Studio** provides specialized visualization for these workflow-specific attributes.

Troubleshooting
===============

No spans appearing
------------------

.. code-block:: python

    # Verify tracer provider is set
    from opentelemetry import trace
    
    tracer = trace.get_tracer("test")
    assert tracer is not None, "Tracer provider not configured"

Missing Junjo attributes
-------------------------

- Junjo attributes are added automatically - no configuration needed
- Verify you're viewing the correct span (workflow vs node)
- Check your platform supports custom attributes

Performance impact
------------------

- OpenTelemetry has minimal overhead (<1% in most cases)
- Use sampling for high-throughput workflows
- Consider async batch exporters for production

Next Steps
==========

- Set up :doc:`junjo_ai_studio` for AI workflow-specific debugging
- Explore :doc:`visualizing_workflows` for static diagrams
- Learn about :doc:`concurrency` to understand parallel execution traces
- Review :doc:`eval_driven_dev` for testing workflows