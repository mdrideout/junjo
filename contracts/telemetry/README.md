# Junjo telemetry contract

This directory is the language-independent compatibility boundary between
Junjo SDK telemetry emitters and Junjo AI Studio consumers.

The active contract version is the integer in `VERSION` and is emitted on each
Junjo executable span as `junjo.telemetry.contract_version`. It is independent
of SDK package versions, Studio versions, and the version of an individual
serialized payload such as the Workflow execution graph snapshot (`v: 2`).

## Ownership

- `schemas/telemetry-fixture.schema.json` describes the normalized fixture
  envelope consumed by compatibility tests.
- `schemas/execution-graph-snapshot.v2.schema.json` describes the JSON string
  stored in `junjo.workflow.execution_graph_snapshot`.
- the Agent schemas describe normalized definition, structural material,
  request, response, Tool, and usage payloads without importing an SDK model;
- `fixtures/workflow` contains canonical normalized Studio API spans for the
  current Workflow lifecycle, state, error, nesting, and concurrency cases.
- `fixtures/agent/producer` is the required producer-conformance scenario set;
  every fixture is produced by actual SDK execution through public Agent and
  Workflow APIs, with bounded private fault injection only for the three
  explicitly Junjo-internal-error scenarios, and drives strict Studio assembly;
- `fixtures/agent/consumer` contains valid evidence modes or transport states
  that a producer-conformance run is not required to emit;
- `fixtures/invalid` contains deterministic corrupt derivatives and their
  expected diagnostic codes;
- `fixtures/fingerprints` and `fixtures/store` contain language-independent RFC
  8785 identity, generated-schema normalization, and RFC 6902 replay vectors;
- `compatibility/generate_v2_fixtures.py` is the canonical fixture generator;
  it removes stale generated cases before writing the complete current set;
- `compatibility/validate_contract.py` performs dependency-free structural and
  semantic validation across every schema and fixture set.

Fixtures are normalized interoperability artifacts. They are not Studio test
implementation details and they are not an SDK's internal object model.

All semantic JSON uses the portable I-JSON domain accepted by the active
contract: finite binary64 numbers, safe integers, unique object names, and
Unicode scalar text. Decoded JSON has a maximum nesting depth of 128: the root
is depth 0, and object names, object values, and array elements are children.
Generated JSON Schemas additionally follow the normative normalization vectors
in `fixtures/fingerprints/schema-normalization-v1.json`.
Semantic consumers validate an already-normalized schema and its fingerprint;
they do not repair or renormalize received evidence.

Event `timeUnixNano` is an exact canonical unsigned 64-bit decimal string.
This transport scalar is intentionally outside the JSON safe-integer model and
must never be coerced through a JSON number. Event ordering comparisons use its
exact integer value; executable operation and Store transition sequences remain
the semantic ordering authorities.

## Application execution correlation

An application may attach one trusted identity to a Junjo execution tree with
the optional executable-owner attributes `junjo.correlation.type` and
`junjo.correlation.id`. The pair is all-or-none, contains nonempty portable
I-JSON text, and propagates unchanged to nested executable owners. Model and
Tool operation spans do not repeat it. Correlation remains distinct from
Junjo definition/runtime identities and OpenTelemetry trace/span identities.

This is an optional governed extension of contract version 2: existing valid
version 2 evidence remains valid without the pair. The canonical
`agent/producer/tool_invokes_nested_workflow` fixture proves propagation across
an Agent, a Tool-owned nested Workflow, and its Nodes. ADR 0007 owns the
application trust and Studio resolution semantics.

## Change rules

For a semantic contract change:

1. decide whether `VERSION` must increase;
2. update schemas and fixtures;
3. update every affected SDK producer test;
4. update Studio ingestion, backend, and frontend consumer tests;
5. run the root validator and all affected component validation.

During current greenfield development, consumers may support only the active
contract version. The version remains explicit so incompatibility is
diagnosable and future language SDKs can prove conformance.

Regenerate and validate from the repository root:

```bash
python3 contracts/telemetry/compatibility/generate_v2_fixtures.py
python3 contracts/telemetry/compatibility/validate_contract.py
git diff --exit-code -- contracts/telemetry
```

Generation must be deterministic and idempotent. Producer implementations are
compared by normalized semantic evidence and successful replay; they are not
required to reproduce incidental language-library JSON Patch operation choices
when multiple RFC 6902 patches describe the same transition.

These interoperability artifacts and the other Junjo-authored platform
components are licensed under the Apache License 2.0. See the repository root
`LICENSE` and the license copies included with independently packaged
components.
