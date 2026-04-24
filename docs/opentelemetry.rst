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
    └── Node Span (declared sink)

Each span includes Junjo-specific attributes that provide workflow context.

Provider Lifecycle
==================

In normal applications, your ``TracerProvider`` and ``MeterProvider`` remain
the top-level owners of OpenTelemetry shutdown. When the process is
terminating, shut down those providers rather than treating exporter-local
flush as the default exit path.

``JunjoOtelExporter`` gives you components to attach to those providers:

- ``span_processor`` for tracing
- ``metric_reader`` for metrics

It also exposes:

- ``shutdown()`` for wrapper-local shutdown of the Junjo-owned components
- ``flush()`` for manual immediate drain when you truly need it

Use ``flush()`` for targeted cases such as tests or short-lived scripts. Use
provider shutdown for the normal application lifecycle.

Library Logging
===============

Junjo emits library logs under the ``junjo`` logger hierarchy. Applications own
handlers, formatting, and log levels.

The main library loggers are:

- ``junjo.workflow``
- ``junjo.node``
- ``junjo.run_concurrent``
- ``junjo.telemetry``

Junjo does not install real log handlers of its own. If you want to see Junjo
execution diagnostics, configure logging in your application and opt in to the
``junjo`` logger namespace.

.. code-block:: python

    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("junjo").setLevel(logging.DEBUG)

With that configuration, Junjo emits debug-level execution progress through the
standard Python logging system without taking over your application's logging
setup.

Runtime log records include run-scoped correlation fields through standard
logging ``extra`` attributes when that execution context exists:

- ``run_id``
- ``executable_definition_id``
- ``executable_runtime_id``
- ``span_type``

Applications using structured logging handlers can capture those fields
directly from the log record without parsing log message text.

Execution failures are logged at the owning workflow or subflow boundary so one
propagated failure produces one library-owned error log instead of multiple
stack traces from each nested execution layer.

Exporter-local warning logs under ``junjo.telemetry`` also include the OTLP
``endpoint`` on the log record so operational failures can be tied back to the
destination that failed.

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

When your Junjo application runs in Docker, it only needs to be on the same
Docker network as the Junjo AI Studio ingestion service. Use ``localhost:26155``
only for applications running directly on the local machine.

.. code-block:: python

    from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
    
    junjo_exporter = JunjoOtelExporter(
        host="ingestion",  # The Junjo AI Studio container name on the same docker network
        port="26155",
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
        host="ingestion",  # The Junjo AI Studio container name on the same docker network
        port="26155",
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

Failed workflow, subflow, node, and concurrent-execution spans also follow the
standard OpenTelemetry error contract in addition to the Junjo-specific fields
below:

- ``error.type`` is set to the exception class name on failed spans.
- span status is set to ``Error``.
- the standard ``exception`` span event is recorded via OpenTelemetry's
  exception recording support.

Cancelled spans do not set ``error.type`` and are not marked with ``Error``
status unless they actually fail.

State Serialization And Telemetry
=================================

Junjo intentionally records rich workflow state in telemetry by default. This
is a debugging-oriented design choice: many AI workflows need full prompts,
tool inputs, tool outputs, and intermediate state to be visible in traces.

Workflow state telemetry is derived from your state model's normal Pydantic
serialization:

- ``junjo.workflow.state.start`` and ``junjo.workflow.state.end`` use the
  serialized state JSON
- ``junjo.state_json_patch`` is built from serialized before/after state dumps

This means your state model controls what appears in OpenTelemetry state
payloads. If you want to exclude, redact, or truncate fields for telemetry,
shape that behavior in your state model serialization.

This does **not** apply to ``junjo.workflow.execution_graph_snapshot``, which
is generated from the compiled graph rather than from state serialization.

Controlling Telemetry State Payloads
------------------------------------

If you need to keep a field in runtime state but remove it from serialized
telemetry payloads, exclude it from Pydantic serialization:

.. code-block:: python

    from pydantic import Field
    from junjo import BaseState


    class ChatWorkflowState(BaseState):
        user_message: str
        llm_response: str | None = None
        raw_api_key: str | None = Field(default=None, exclude=True)

In this example, ``raw_api_key`` remains available in runtime state, but it is
omitted from serialized OpenTelemetry state snapshots and JSON patches.

If you want to keep a field but truncate or reshape it for telemetry, use a
serializer on the state model:

.. code-block:: python

    from pydantic import field_serializer
    from junjo import BaseState


    class PromptWorkflowState(BaseState):
        prompt: str
        final_answer: str | None = None

        @field_serializer("prompt")
        def serialize_prompt_for_telemetry(self, value: str) -> str:
            if len(value) <= 2000:
                return value
            return value[:2000] + "...[truncated]"

In this example, runtime state still holds the full prompt, but Junjo's
OpenTelemetry state fields and patches use the truncated serialized form.

Hook Events Use Copied State Objects
------------------------------------

Hook event state payloads are separate from OpenTelemetry serialization.

- OpenTelemetry state fields use serialized state from your model
- hook ``event.state`` values use a copied in-memory state object

So excluding or truncating a field for telemetry serialization does **not**
automatically remove it from ``event.state`` inside hook callbacks.

Workflow/Subflow Span Attributes
---------------------------------

.. code-block:: python

    {
        "junjo.span_type": "workflow" | "subflow",
        "junjo.executable_definition_id": "<workflow-definition-id>",
        "junjo.executable_runtime_id": "<workflow-run-id>",
        "junjo.executable_structural_id": "<graph-structural-id>",
        "junjo.enclosing_graph_structural_id": "<graph-structural-id>",
        "junjo.workflow.state.start": "<initial-state-json>",
        "junjo.workflow.state.end": "<final-state-json>",
        "junjo.workflow.execution_graph_snapshot": "<execution-graph-snapshot-json>",
        "junjo.workflow.node.count": 5,
        "junjo.workflow.store.id": "<store-id>",
        
        # Subflow only:
        "junjo.parent_executable_definition_id": "<parent-workflow-definition-id>",
        "junjo.parent_executable_runtime_id": "<parent-executable-runtime-id>",
        "junjo.parent_executable_structural_id": "<parent-executable-structural-id>",
        "junjo.workflow.parent_store.id": "<parent-store-id>"
    }

Node Span Attributes
--------------------

.. code-block:: python

    {
        "junjo.span_type": "node",
        "junjo.executable_definition_id": "<node-definition-id>",
        "junjo.parent_executable_definition_id": "<parent-workflow-or-subflow-definition-id>",
        "junjo.executable_runtime_id": "<node-runtime-id>",
        "junjo.executable_structural_id": "<node-structural-id>",
        "junjo.parent_executable_runtime_id": "<parent-executable-runtime-id>",
        "junjo.parent_executable_structural_id": "<parent-executable-structural-id>",
        "junjo.enclosing_graph_structural_id": "<graph-structural-id>"
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
        
        # Configure Junjo AI Studio exporter.
        junjo_exporter = JunjoOtelExporter(
            host="ingestion",  # The Junjo AI Studio container name on the same docker network
            port="26155",
            api_key=api_key,
            insecure=not is_production  # True for local dev, False for production
        )
        
        # Add span processor
        tracer_provider.add_span_processor(junjo_exporter.span_processor)
       
        # Configure metrics with the Junjo metric reader
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[junjo_exporter.metric_reader]
        )
        metrics.set_meter_provider(meter_provider)

        # Set as global tracer provider
        trace.set_tracer_provider(tracer_provider)

        return tracer_provider, meter_provider

Use in your application:

.. code-block:: python

    from otel_config import init_telemetry
    
    tracer_provider, meter_provider = init_telemetry(service_name="my-ai-workflow")

    try:
        # Execute workflows - automatic instrumentation
        await my_workflow.execute()
    finally:
        tracer_provider.shutdown()
        meter_provider.shutdown()

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
