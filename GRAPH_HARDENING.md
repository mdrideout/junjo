# Junjo Graph Hardening Plan

This document defines the graph-specific hardening direction for Junjo.

It focuses on the graph topology model, traversal semantics, validation,
serialization, rendering, and graph identity. Runtime execution isolation,
store correctness, hooks, and telemetry hardening are tracked elsewhere.

## Goals

- Keep graph terminology conventional and intuitive for both developers and
  LLMs.
- Make graph traversal semantics explicit and testable.
- Make graph serialization internally consistent and deterministic.
- Keep telemetry runtime IDs unique while also introducing stable structural
  IDs for graph identity.
- Fail invalid graph shapes intentionally through typed exceptions instead of
  incidental runtime behavior.

## Completed Since Draft

- Subflow serialization now reuses one child graph snapshot per serialization
  pass, so source and sink references are internally consistent within a
  single payload.
- Subflow edge IDs now include an ordinal, so multiple same-tail/head edges
  are preserved during serialization.
- ``Graph`` now uses explicit plural ``sinks`` instead of a singular
  ``sink``.
- Runtime traversal now follows ordered first-match semantics directly: the
  first declared matching edge wins, and later edges are not evaluated.
- Graph serialization now raises a typed ``GraphSerializationError`` instead
  of returning an error-shaped JSON payload.
- ``Graph.validate()`` now exists and workflow/subflow execution validates the
  fresh graph by default before any nodes run.
- Validation can be disabled per execution with ``validate_graph=False`` for
  targeted tests and debugging.
- ``Graph.compile()`` now builds one canonical compiled graph snapshot per
  graph instance, and validation, traversal adjacency, and serialization all
  consume that shared structural representation.

## Terminology Decisions

### Source

Junjo should keep the term ``source``.

It is conventional graph terminology, intuitive in directed workflow graphs,
and already maps well to the execution model:

- execution begins at the single source node

### Sink vs Sinks

Junjo should move from a singular ``sink`` to explicit plural ``sinks``.

The conceptual model should be:

- ``source`` is the single entry node
- ``sinks`` are the explicit terminal nodes

Docs may also describe sinks as *terminal nodes* for readability, but the API
should remain graph-native.

Junjo should not infer terminal nodes implicitly from “no outgoing edge,”
because that turns graph mistakes into silent successful termination.

### Ordered Edge Resolution

Ordered edge resolution is intentional behavior and should remain so.

The contract should be:

- outgoing edges are evaluated in the order they are declared
- the first edge whose condition resolves true is selected
- later edges are not evaluated once a match is found

This is not an ambiguity bug. It is a graph semantics rule and should be
documented, validated where possible, and tested directly.

## Current Graph Risks

No open graph-specific correctness risks are currently tracked in this plan.

The major graph hardening phases below are now complete. Future graph work can
be tracked as separate product expansion rather than unresolved hardening
debt.

## Design Direction

### 1. Separate Runtime IDs From Structural IDs

Junjo should keep runtime-generated IDs for telemetry and live execution.

Those IDs are still valuable because they provide total uniqueness in traces
and telemetry exports.

Junjo should also add a second identity layer:

- runtime IDs for execution uniqueness
- structural IDs for graph-shape identity

Structural IDs should be:

- deterministic for the same graph structure
- stable across repeated factory calls
- used for rendering, graph diffing, and graph-shape comparison
- included alongside runtime IDs, not instead of them

This means the graph layer should stop treating runtime IDs as the only graph
identity available.

Identity keys should also be self-describing without requiring surrounding
context. Public field names and telemetry attributes should say both what they
identify and what kind of identity they carry. Examples:

- ``graph_structural_id``
- ``node_structural_id``
- ``edge_structural_id``
- ``junjo.executable_runtime_id``
- ``junjo.parent_executable_structural_id``

### 2. Introduce A Canonical Compiled Graph Snapshot

Status: complete

Junjo should compile a graph definition into one canonical structural snapshot
before:

- validation
- traversal planning
- serialization
- Graphviz export
- Mermaid export

The compiled graph should:

- contain a single internally consistent view of all nodes, edges, subflows,
  and concurrent groups
- assign stable structural node IDs and structural edge IDs
- preserve declared edge ordering
- avoid re-instantiating subflow graphs multiple times during the same compile
  or serialization pass

This compiled snapshot becomes the foundation for every graph-facing feature.

Graphviz and Mermaid rendering now consume the compiled snapshot directly.

### 3. Move To Explicit ``sinks``

The graph API should support multiple explicit terminal nodes.

Recommended target API:

.. code-block:: python

    Graph(
        source=start_node,
        sinks=[approved_node, rejected_node, timeout_node],
        edges=[...],
    )

Execution should terminate when the current executable reaches any declared
sink.

Junjo should not rely on implicit “no outgoing edges means terminal” behavior.

### 4. Codify Ordered First-Match Traversal

Traversal should follow the first valid edge in declared order.

This should become explicit in both code and docs:

- resolve outgoing edges in list order
- return immediately on first match
- raise only if no outgoing edge resolves

This is more efficient and more closely matches the intended developer mental
model than evaluating all edges and then picking the first resolved one.

## Validation Rules

The future ``Graph.validate()`` or compile-time validation phase should check
at least the following:

### Required Topology

- exactly one ``source``
- at least one sink in ``sinks``
- every sink belongs to the graph
- source belongs to the graph
- every edge tail and head belong to the graph

### Terminal Rules

- sinks must be explicit
- sinks should not have outgoing edges
- any executable that is intended to be terminal must appear in ``sinks``

### Reachability / Structural Soundness

- detect unreachable declared sinks
- detect unreachable nodes included through the graph structure
- detect executables reachable from source that have no outgoing edge and are
  not declared sinks

### Subflow / Concurrent Structure

- validate nested subflow graphs recursively
- validate that concurrent child items are structurally representable in the
  compiled snapshot

### Traversal Semantics

- preserve edge ordering exactly as declared
- do not reject ordered branching just because multiple conditions *could*
  evaluate true; ordered first-match is allowed behavior

### Things Validation Should Not Reject

- loops in general
- retry cycles
- review/revise cycles

Those remain runtime concerns controlled by iteration limits, not graph-shape
validation failures.

## Typed Exceptions

Graph hardening should introduce typed exceptions instead of broad
``ValueError`` or JSON-shaped failure payloads.

Recommended exception types:

- ``GraphValidationError``
- ``GraphCompilationError``
- ``GraphSerializationError``
- ``GraphRenderError``

These exceptions should make it obvious whether the failure came from:

- invalid topology
- failed compilation
- serialization inconsistency
- Graphviz or Mermaid rendering failure

## Phased Implementation Plan

### Phase 1 - Serialization Correctness

Status: complete

### Scope

- compile each graph only once per serialization pass
- fix subflow source/sink reference consistency
- prevent subflow edge ID collisions
- replace JSON fallback payloads with typed serialization errors

### Exit Criteria

- one serialized graph payload is always internally consistent
- subflow source and sink IDs point to nodes present in the same payload
- multiple subflow edges with the same tail/head pair are preserved
- serialization failures raise typed exceptions

### Phase 2 - Explicit Terminal Nodes

Status: complete

### Scope

- evolve the graph model from singular ``sink`` to explicit ``sinks``
- make terminal nodes explicit in traversal
- validate that sinks do not have outgoing edges
- update docs/examples to describe sinks as terminal nodes

### Exit Criteria

- graphs can terminate at any explicit sink
- artificial “single final join node” wiring is no longer required
- traversal exits when any sink is reached
- validation rejects illegal outgoing edges from sinks

### Phase 3 - Graph Compilation And Validation

Status: complete

### Scope

- introduce a canonical compiled graph snapshot
- implement ``Graph.validate()`` or equivalent compile-time validation
- codify ordered first-match traversal semantics
- validate reachable non-sink dead ends
- validate recursive subflow structures

### Exit Criteria

- invalid graphs fail before traversal where possible
- traversal semantics are explicit and documented
- compiled graph shape is reusable across validation and serialization

### Phase 4 - Structural IDs

Status: complete

### Scope

- add stable structural IDs for graphs, nodes, and edges
- keep runtime IDs for execution uniqueness
- include both runtime and structural IDs in telemetry-facing graph payloads
- expose explicit runtime and structural identity names in hooks and telemetry
- use structural IDs for graph rendering and diffing

### Exit Criteria

- the same graph shape produces the same structural IDs across runs
- runtime IDs remain unique for telemetry
- graph-shape identity is separable from execution identity
- telemetry and hooks expose explicit runtime and structural identity fields

### Phase 5 - Rendering Hardening

Status: complete

### Scope

- make Graphviz export depend on the compiled structural snapshot
- implement Mermaid output from the compiled structural snapshot
- ensure render/export failures use typed exceptions

### Exit Criteria

- Graphviz output is based on the compiled graph model
- Mermaid output is based on the compiled graph model
- rendering errors are typed and explicit

## Testing Plan

Graph hardening should add focused tests for:

- subflow serialization consistency within one payload
- preservation of multiple subflow edges sharing the same tail/head pair
- ordered first-match traversal semantics
- illegal outgoing edges from sinks
- reachable dead-end non-sinks
- multi-sink successful termination
- structural ID stability across repeated graph factories
- typed exceptions for validation vs serialization vs rendering

## Recommended Order

1. Fix same-pass serialization correctness bugs
2. Introduce explicit ``sinks``
3. Add compile/validate phase
4. Add structural IDs
5. Harden rendering/export

## Final Position

The graph model should remain graph-native and explicit:

- one ``source``
- one or more explicit ``sinks``
- ordered edges
- optional edge conditions

Junjo should keep runtime IDs for telemetry, while adding structural IDs for
graph identity. The near-term priority is not graph-shape diffing in the
abstract; it is making every single serialized graph payload internally
consistent and trustworthy.
