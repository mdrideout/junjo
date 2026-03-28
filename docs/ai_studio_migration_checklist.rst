AI Studio Migration Checklist
=============================

This page tracks the frontend and schema updates required in
``junjo-ai-studio`` after Junjo's telemetry and graph payload refactors.

Telemetry Key Renames
---------------------

Replace the older generic telemetry keys with the explicit executable identity
keys now emitted by Junjo:

- ``junjo.id`` -> ``junjo.executable_runtime_id``
- ``junjo.parent_id`` -> ``junjo.parent_executable_runtime_id``
- ``junjo.definition_id`` -> ``junjo.executable_definition_id``
- ``junjo.parent_definition_id`` -> ``junjo.parent_executable_definition_id``
- ``junjo.workflow.graph_structure`` -> ``junjo.workflow.execution_graph_snapshot``

Graph Snapshot Schema Updates
-----------------------------

The execution graph snapshot now carries explicit runtime and structural
identity fields.

Update AI Studio graph schemas from the older generic shape:

- node ``id`` -> ``nodeRuntimeId`` and ``nodeStructuralId``
- edge ``id`` -> ``edgeStructuralId``
- edge ``source`` -> ``tailNodeRuntimeId``
- edge ``target`` -> ``headNodeRuntimeId``
- edge ``condition`` -> ``edgeConditionLabel``
- edge ``subflowId`` -> ``parentSubflowRuntimeId``
- graph top-level ``graphStructuralId`` is now present
- subflow node ``subflowSourceId`` -> ``subflowSourceNodeRuntimeId``
- subflow node ``subflowSinkId`` -> ``subflowSinkNodeRuntimeIds``
- subflow node now also carries:
  - ``subflowGraphStructuralId``
  - ``subflowSourceNodeStructuralId``
  - ``subflowSinkNodeStructuralIds``

Mermaid Node Matching Rules
---------------------------

AI Studio should no longer assume one universal Junjo ID field.

Use these matching rules instead:

- Normal nodes and ``RunConcurrent`` nodes:
  ``nodeRuntimeId`` <-> ``junjo.executable_runtime_id``
- Subflow nodes in the parent graph:
  ``subflowGraphStructuralId`` <-> ``junjo.executable_structural_id``
- When definition-level matching is needed for subflow container nodes:
  parent graph ``nodeRuntimeId`` <-> ``junjo.executable_definition_id``

Trace Tree And Parentage
------------------------

The OpenTelemetry trace tree should continue to use standard OTEL
``parent_span_id`` for span ancestry.

Junjo-specific parent executable fields are still valuable for UI features that
need execution-level relationships:

- ``junjo.parent_executable_definition_id``
- ``junjo.parent_executable_runtime_id``
- ``junjo.parent_executable_structural_id``

Migration Outcome
-----------------

After this migration, AI Studio should be able to:

- parse the new execution graph snapshot payload
- map rendered graph nodes back to spans using explicit runtime and structural ids
- preserve trace-tree behavior using OTEL ``parent_span_id``
- support stable cross-run graph aggregation using structural ids
