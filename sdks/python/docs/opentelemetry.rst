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
- Agent execution (definition, normalized model/Tool operations, state,
  usage, limits, and terminal outcome)
- Individual node execution
- Subflow execution with parent relationships
- RunConcurrent concurrent execution
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

Agent hierarchy and ownership
-----------------------------

An Agent is an executable owner span, not a synthetic Workflow. Model requests
and Tool calls are ordered operation spans owned by that Agent run:

.. code-block:: text

    Agent
    ├── model request 1
    ├── tool lookup
    │   └── Workflow                 (when the Tool invokes a Workflow)
    │       └── Node
    └── model request 2

An Agent invoked by a Workflow Node is physically and semantically nested
under that Node. A standalone Agent under a non-Junjo server span preserves the
physical OpenTelemetry parent but does not fabricate Junjo semantic-parent
attributes. Nested Agent owners each restart their own operation sequence,
Store revisions, usage aggregate, limits, and terminal evidence.

Owner spans distinguish definition, run, and structural identity:

* ``junjo.executable_definition_id`` identifies the definition object;
* ``junjo.executable_runtime_id`` and ``junjo.agent.runtime_id`` identify the
  current run;
* ``junjo.executable_structural_id`` is the deterministic ``agent_sha256``
  behavior fingerprint.

``junjo.parent_executable_*`` records the nearest semantic Junjo owner when
one exists. Those values intentionally may skip an operation span: a Workflow
physically started inside a Tool is semantically parented by the Agent because
the Tool is not an executable definition owner.

Every Junjo executable span includes
``junjo.telemetry.contract_version``. This integer identifies the
language-independent contract used by SDK emitters and Studio consumers; it is
separate from the Python package version and from payload-specific schema
versions such as the execution graph snapshot's ``v`` field.

Agent evidence and Store replay
-------------------------------

The Agent owner contains its definition snapshot, normalized input, start/end
state, aggregate usage, exact limits and counters, output when successful, and
one terminal outcome. Model operation spans contain the immutable request,
raw portable response candidate when available, validated normalized response,
descriptor identity, usage, ordinal, operation sequence, and state revision.
Tool operation spans similarly distinguish requested arguments, admitted
validated arguments, service result candidate, validated result, call identity,
ordinal, sequence, and before/after revisions.

Agent state transitions use the same observable Store protocol as Workflows.
Each ``set_state`` event includes:

* ``junjo.store.action`` and a contiguous transition sequence;
* before/after revisions (no-op transitions do not advance revision);
* a portable RFC 6902 patch and its payload mode/policy;
* the owner Store identity.

Studio and conformance consumers collect events across the owner and its
operation spans, order them by transition sequence, replay from
``junjo.agent.state.start``, and require the result to equal
``junjo.agent.state.end``. The Agent action grammar exposes model start and
response, whole-batch admission, Tool start/result, and one terminal commit.
``junjo.store.reconstructable`` is false only when complete replay cannot be
claimed, such as a failed terminal Store commit.

All contract payload slots explicitly report ``.mode`` and ``.policy``. The
SDK's core policy is ``full`` / ``junjo.full.v1``; absence is never silently
interpreted as redaction. Unavailable model or Tool candidates instead carry
an explicit availability flag and reason such as ``not_returned``,
``not_json_serializable``, ``not_invoked``, or ``cancelled``. Every full JSON
payload obeys the portable I-JSON boundary described in :doc:`agents`.

In Junjo AI Studio, begin diagnosis at the Agent owner: verify outcome,
termination reason, evidence completeness, and Store reconstruction. Then
follow operation sequence to the first failed/cancelled Model or Tool span and
inspect candidate-versus-validated payload slots. Semantic parent identities
show whether the Agent was invoked directly, by a Workflow Node, or around a
nested Workflow. Evidence-loss counters and non-full payload policies must be
shown as diagnostic limitations rather than treated as application behavior.

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
        host="ingestion",  # The AI Studio ingestion service name on your Docker network ("ingestion" in the example compose file)
        port="26155",
        api_key=api_key,
        insecure=True
    )
    tracer_provider.add_span_processor(junjo_exporter.span_processor)

For production, use the public Junjo AI Studio ingestion host and TLS:

.. code-block:: python

    from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter

    junjo_exporter = JunjoOtelExporter(
        host="ingestion.example.com",
        port="443",
        api_key=api_key,
        insecure=False
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
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    
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
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    
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
        host="ingestion",  # The AI Studio ingestion service name on your Docker network ("ingestion" in the example compose file)
        port="26155",
        api_key=junjo_api_key,
        insecure=True
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

Failed Workflow, Subflow, Node, concurrent-execution, Agent, model-request, and
Tool spans also follow the standard OpenTelemetry error contract in addition
to the Junjo-specific fields below:

- ``error.type`` is set to the exception class name on failed spans.
- span status is set to ``Error``.
- Junjo constructs the standard ``exception`` span event fields from its
  non-throwing portable diagnostic projection, so hostile exception formatting
  cannot replace the execution outcome or produce invalid telemetry text.

Cancelled spans use Junjo-specific cancellation attributes instead of the
standard error fields:

- ``junjo.cancelled`` is set to ``true``.
- ``junjo.cancelled_reason`` describes why the operation was cancelled.

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

Junjo applies those serialization choices only when producing telemetry
payloads. Runtime state transitions still use the state object's field values,
so excluded or serialized fields are not removed or rewritten by later
``set_state`` calls.

This does **not** apply to ``junjo.workflow.execution_graph_snapshot``, which
is generated from the compiled graph rather than from state serialization.
See :doc:`junjo_ai_studio` for the AI Studio identity and execution graph
snapshot contract.

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

RunConcurrent Span Attributes
-----------------------------

.. code-block:: python

    {
        "junjo.span_type": "run_concurrent",
        "junjo.executable_definition_id": "<run-concurrent-definition-id>",
        "junjo.parent_executable_definition_id": "<parent-workflow-or-subflow-definition-id>",
        "junjo.executable_runtime_id": "<run-concurrent-runtime-id>",
        "junjo.executable_structural_id": "<run-concurrent-structural-id>",
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
        
        # Get API key
        api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
        if not api_key:
            raise ValueError("JUNJO_AI_STUDIO_API_KEY environment variable not set")
        
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
            host="ingestion",  # The AI Studio ingestion service name on your Docker network ("ingestion" in the example compose file)
            port="26155",
            api_key=api_key,
            insecure=True
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

Production Junjo AI Studio Exporter
===================================

For production, configure ``JunjoOtelExporter`` with the public ingestion host
and TLS:

.. code-block:: python

    junjo_exporter = JunjoOtelExporter(
        host="ingestion.example.com",
        port="443",
        api_key=api_key,
        insecure=False
    )

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
- Learn about :doc:`concurrency` to understand concurrent execution traces
- Review :doc:`eval_driven_dev` for testing workflows
