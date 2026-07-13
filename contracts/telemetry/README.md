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
- `fixtures/workflow` contains canonical normalized Studio API spans for the
  current Workflow lifecycle, state, error, nesting, and concurrency cases.
- `compatibility/validate_contract.py` performs dependency-free structural and
  version validation.

Fixtures are normalized interoperability artifacts. They are not Studio test
implementation details and they are not an SDK's internal object model.

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

Run the standalone validation from the repository root:

```bash
python3 contracts/telemetry/compatibility/validate_contract.py
```

These interoperability artifacts and the other Junjo-authored platform
components are licensed under the Apache License 2.0. See the repository root
`LICENSE` and the license copies included with independently packaged
components.
