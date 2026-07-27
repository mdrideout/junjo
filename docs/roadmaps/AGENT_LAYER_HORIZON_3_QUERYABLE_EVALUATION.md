# Horizon 3: Queryable Evaluation System And Iterative MVP Plan

- Status: Active planning
- Date: 2026-07-27
- Owners: Junjo platform
- Parent roadmap:
  [Junjo Agent Layer Strategy And Roadmap](AGENT_LAYER_ROADMAP.md)

## Document Role

This document is the working source of truth for Horizon 3 planning. It turns
the high-level Agent roadmap into an iterative implementation sequence that can
be refined as real evaluation evidence exposes the required contracts.

This is not an accepted runtime or telemetry contract. Accepted ADRs continue
to own implemented architecture. Before a Horizon 3 slice changes a shared SDK,
telemetry, ingestion, Studio, or authentication contract, that decision must be
accepted in the owning ADR and implemented across every affected component.

## Product Thesis

Horizon 3 makes Junjo AI Studio the queryable evidence and evaluation control
plane for an open, application-executed evaluation loop:

1. applications export OpenTelemetry traces and spans to Studio;
2. developers and coding agents select historical evidence or author new cases;
3. applications may deliberately execute a real Node, Agent, Workflow, or
   complete application flow to generate labeled dataset evidence;
4. Studio organizes exact evidence references into immutable dataset versions;
5. an open harness pulls those cases and executes candidate prompts, models,
   Tools, Nodes, Agents, Workflows, or complete flows through the real Junjo
   lifecycle;
6. the supported evidence successfully exported and received returns to Studio
   as clearly classified evaluation telemetry;
7. Studio compares results and complete execution evidence from the changed
   upstream prompt through every downstream consequence; and
8. developers and coding agents query the evidence, revise the application, and
   repeat.

Studio already preserves received prompts, responses, state, Tool evidence,
images or image references, and the supported trace hierarchy emitted by the
application. Horizon 3 does not introduce file bundles, browser uploads, or a
second trace store. Dataset and experiment records organize the canonical
evidence already in Studio.

```text
Real application runs --------------------+
                                          |
Deliberate dataset-generation runs -------+--> Studio trace evidence
                                          |          |
Programmatically authored literal cases --+          v
                                             versioned datasets
                                                    |
                                                    v
                                         application eval harness
                                                    |
                                      candidate execution + evaluators
                                                    |
                                                    v
                                         labeled evaluation traces
                                                    |
                                                    v
                                      result + end-to-end comparison
                                                    |
                                                    v
                                          developer or coding agent
```

## Horizon 3 Goals

Horizon 3 must:

- create datasets from historical trace, executable, operation, state, and
  output evidence;
- create cases programmatically without requiring the application server or
  browser to run;
- deliberately execute real application code to generate complete labeled
  evidence for a new dataset;
- support focused entity datasets and complete end-to-end flow datasets;
- preserve the causal relationship between an upstream prompt or model call and
  every downstream execution effect;
- identify state-schema, prompt-template, candidate, dataset, evaluator, model,
  and execution shapes precisely enough to make comparisons truthful;
- classify application, dataset-generation, and evaluation traffic clearly;
- let coding agents query, create, run, and compare evaluations through stable
  programmatic contracts;
- keep evaluators open to ordinary application code, deterministic checks,
  model judges, external verifiers, and human review; and
- retain Studio's bounded-memory hot/cold ingestion and query architecture.

## Explicit Non-Goals

Horizon 3 does not add:

- file-based trace or result import;
- browser upload as the dataset creation model;
- a duplicate rendered-prompt, conversation, image, or trace-payload evidence
  store;
- arbitrary uploaded source execution inside Studio;
- magical replay that claims telemetry can recreate application code,
  dependencies, credentials, databases, or external-world state;
- a second OTLP receiver or evaluation-specific telemetry warehouse;
- raw SQL, Parquet paths, or DataFusion plans as a public agent API;
- a generalized distributed scheduler or case-leasing platform;
- a vector database without a proven retrieval requirement;
- automatic prompt editing, source modification, or promotion;
- probabilistic evaluation as a required default CI gate; or
- a separate MCP query implementation with semantics that diverge from the
  Studio API.

## Current Foundation

Horizon 3 builds on implemented behavior:

- Studio ingestion preserves the supported attributes, events, links, resource
  evidence, parentage, and evidence-loss counters it receives in the existing
  hot/cold Parquet evidence plane.
- Studio `TraceEvidence` returns all normalized evidence found for a trace plus
  verified Workflow, Agent, Store, operation, relationship, and integrity
  annotations.
- Workflow and Subflow telemetry records Graph structure, start and end state,
  ordered Store transitions, executable runtime identity, and structural
  identity.
- Agent telemetry records the definition snapshot, exact instructions, input,
  output, normalized model requests and responses, Tools, usage, limits, and
  nested execution evidence.
- `evaluate_node()` executes a real Node through a truthful one-Node Workflow
  rather than bypassing Junjo's lifecycle.
- `ExecutionCorrelation` preserves application-domain identity across a Junjo
  execution tree.
- AI Chat has live Node, Agent, and Workflow evaluations and local JSON result
  artifacts linked to exact Studio executions.

Material gaps remain:

- Studio has no Dataset, DatasetVersion, EvaluationDefinition, Experiment,
  EvaluationRun, or comparison domain.
- Existing Studio list routes are shaped for current UI screens rather than
  semantic dataset construction.
- Node and RunConcurrent spans have useful identity but do not yet receive the
  same typed Studio executable projection as Workflow, Subflow, and Agent.
- AI Chat evaluation traces are not labeled consistently and cannot be reliably
  separated from application traffic.
- Scores, dataset versions, prompt labels, and judge results currently live in
  local files rather than a Studio evaluation domain.
- Workflow state values are recorded, but their state schema is not
  fingerprinted.
- Workflow Node prompts are ordinary rendered strings. Their originating
  template and variable contract cannot be recovered from the final string.
- Workflow and Node structural IDs describe Graph position and topology, not
  prompt content, state schema, implementation, or complete candidate behavior.
- Junjo Agent model requests have a portable normalized contract; arbitrary
  provider-instrumented model spans do not yet share one generic re-execution
  contract.
- The current `llm_traces` file hint recognizes OpenInference and OpenTelemetry
  GenAI attributes but not native Junjo Agent model-operation spans. Horizon 3
  model-operation search cannot reuse that hint unchanged.
- The Python producer currently emits full payload evidence. Studio's consumer
  contract also understands redacted, excluded, and reference evidence from
  conforming producers.
- Coding agents have no stable Studio dataset, experiment, or semantic evidence
  client.

No trace is presumed complete merely because execution returned or an exporter
flush succeeded. Sampling, batching, queue pressure, transport failure, process
termination, or downstream persistence failure can leave partial evidence.
Dataset generation records trace integrity and readiness explicitly. Freezing a
generated set requires a declared policy for complete, partial, or unknown
evidence and must never silently treat missing spans as a complete run.

## Working Vocabulary

The following concepts keep evidence identity, dataset meaning, and execution
scope separate.

### Evidence Entity

One addressable part of canonical Studio evidence. An entity may be a complete
trace, a Junjo executable, a model or Tool operation, a Store boundary, or a
Store transition.

### Selection Anchor

An exact locator for canonical evidence. Historical identity ultimately uses
an OpenTelemetry trace ID and, where applicable, a span ID. Runtime IDs,
structural IDs, service identity, Agent keys, correlation, time, outcome, and
artifact fingerprints are search facets that resolve to exact anchors.

### Projection

A named evaluator-facing view over an anchored entity, such as an Agent output,
model response, Workflow end state, Node state delta, Tool result, or complete
execution subtree. A projection does not create another copy of the trace.

### Dataset Case

One stable case in a dataset version. It contains named members whose sources
are either exact evidence references or intentionally authored literal values.
It also identifies what should be executed and what evidence scope should be
compared.

### Focal Entity

The exact entity whose behavior is being tested, such as a prompt-bearing model
operation or a date-response Node.

### Comparison Scope Root

The execution envelope whose complete effects matter. It may be wider than the
focal entity.

For example, a model request inside a Node may be the focal entity while the
containing Turn Workflow is the comparison scope root. Later Workflow Nodes are
not physical descendants of the inner model span, but they are causally
downstream of its changed result.

### Generated Evidence Set

The complete subject evidence produced by one deliberate dataset-generation or
candidate execution. It contains one or more subject roots, a versioned
membership rule, exact anchors for explicitly named members, and optional
bounded closure count/fingerprint evidence. Studio derives the complete
physical descendant closure and verified nested-executable relationships on
demand rather than storing a searchable row for every descendant span.

A case attempt that fails before subject admission has no subject root and
therefore no generated evidence set. Its orchestrator trace records the
pre-subject failure directly.

### Dataset Draft And Dataset Version

A draft is mutable curation work. A version is an immutable, ordered set of
cases with a content fingerprint. Experiments always run an immutable version.

### Evaluation Definition

A versioned description of what is measured: evaluator keys, rubric or
criteria, result schema, configuration, and judge or verifier identity.
Evaluator code remains application-executed unless a later accepted decision
defines a safe declarative evaluator.

### Candidate

One immutable subject configuration being measured. It identifies relevant
prompt, model, schema, Tool, executable, configuration, and implementation
artifacts independently from its human label.

### Evaluation Run

One attempt to evaluate a dataset version and evaluation definition against a
candidate. Each case attempt has exact subject and evaluator evidence.

## Dataset Case Origins

Horizon 3 supports three complementary origins.

### Historical Evidence

A developer or coding agent queries existing application evidence, selects
exact entities, and adds them to a dataset draft.

Examples:

- a set of failed Agent run IDs;
- all date-response Nodes selected from a bounded service and time range;
- exact model-operation spans that produced hallucinated places;
- complete Turn Workflows whose final answer violated a constraint; or
- a Workflow execution plus selected intermediate Store transitions.

Freezing the dataset resolves every dynamic selection to exact anchors. A
future run never silently receives a different historical cohort.

### Authored Literal Cases

A developer or coding agent creates portable input, expected values, rubric
references, tags, and execution configuration directly through the Studio API.
No application server or prior trace is required.

The authored input is dataset content because no historical evidence exists.
When the case is first executed, its complete resulting telemetry becomes
canonical Studio evidence and is linked to the case attempt.

### Deliberate Dataset-Generation Runs

A developer or coding agent starts a dataset capture and executes a real Node,
Agent, Workflow, Subflow envelope, or complete application path. The execution
uses live application code and dependencies and emits normal complete
telemetry.

The run is explicitly classified as dataset generation rather than ordinary
application use. After expected trace evidence reaches Studio and readiness is
evaluated:

1. Studio resolves the declared subject root;
2. it derives, within hard limits, every executed Workflow, Subflow,
   RunConcurrent, Node, Agent, model operation, Tool operation, Store boundary,
   transition, and known typed payload slot in scope;
3. it records subject roots, the membership-algorithm version, bounded
   count/fingerprint evidence, and exact anchors only for named members;
4. the author may add the complete flow, selected entities, or both to the
   dataset draft; and
5. freezing the dataset records the roots, membership rule, and final exact
   named membership.

If real evidence proves that a frozen closure snapshot is required, it must be
one size-capped immutable manifest blob. It must not become row-per-entity
control metadata or a generic per-span search index.

Dataset-generation failures are valid evidence. A failed Node, provider call,
Tool, Agent, or Workflow remains selectable and must not disappear merely
because the generation run did not complete successfully. The outer
case-attempt span also records setup or admission failures that occur before a
Junjo subject owner span and runtime ID exist; those pre-subject attempts do not
produce a generated evidence set.

Conceptually, the application-side flow is:

```python
capture = local_dataset_capture(
    case_id="park-slope-under-40",
    subject_kind="workflow",
)

with capture.telemetry_scope():
    result = await turn_workflow.execute(...)

generated_set = await studio.datasets.attach_capture(
    dataset_draft_id="local-place-realism",
    capture_id=capture.id,
    subject_run_id=result.run_id,
)
```

These names are illustrative, not an accepted API. The important contract is
that capture identity exists before execution, the real execution emits normal
telemetry, and Studio resolves the resulting evidence afterward instead of
receiving an uploaded trace or result bundle. A runner can create the capture
ID locally, so Studio availability is not a prerequisite for executing the
case. Studio-initiated pre-registration may be added later as an optional UI
convenience.

Every entity in the bounded resolved closure is logically associated with that
generated evidence set through its roots and membership rule. Studio does not
retroactively rewrite stored spans to add dataset labels. Membership does not
force every entity to become an independent dataset case. It makes the complete
flow available while the author chooses which entities become focused cases or
named case members.

## Execution Capture Scopes

The initial execution capture scopes are:

| Capture mode | Execution path | Primary subject | Complete evidence scope |
| --- | --- | --- | --- |
| Node | `evaluate_node()` | Node state effect and child model calls | Truthful one-Node evaluation Workflow |
| Agent | `Agent.execute()` | Agent input, output, model/Tool sequence | Agent descendant closure |
| Workflow | `Workflow.execute()` | Workflow input/state, selected path, final state | Workflow descendant closure |
| Subflow | Application-owned enclosing execution | Child Store boundaries, observable parent/child Store effects, and internal Graph | Subflow closure or containing Workflow |
| Complete application flow | Application-owned service or direct use-case entry point | User-visible action | Declared trace subject roots |

A Subflow does not yet need a new public isolated execution helper. The first
implementation should exercise it through an application-owned enclosing
Workflow. A dedicated helper is justified only if the vertical proof shows a
real repeated need.

## Labeled Evaluation Entity Taxonomy

Horizon 3 must distinguish addressable evidence entities from independently
executable targets. Not every useful entity should become a new runtime
abstraction.

### Execution Containers

| Entity | Exact anchor | Useful projections | Candidate execution scope |
| --- | --- | --- | --- |
| Trace / complete flow | Trace ID | Complete trace evidence and raw span tree | Application-owned entry point |
| Workflow | Workflow owner span | Graph, start/end state, Store timeline, selected path, subtree | `Workflow.execute()` |
| Subflow | Subflow owner span | Internal Graph, child Store boundaries, observable parent/child Store effects, subtree | Enclosing Workflow initially |
| RunConcurrent | RunConcurrent span | Branch subtree and directly attributable Store transitions; aggregate boundary only when proven | Enclosing Workflow initially |

### Executable And Operation Entities

| Entity | Exact anchor | Useful projections | Candidate execution scope |
| --- | --- | --- | --- |
| Node | Node span | Directly attributable Store transitions, conditional entry/exit state, provider child spans, subtree | `evaluate_node()` or containing Workflow |
| Agent | Agent owner span | Definition, input/output, operations, state, usage, subtree | `Agent.execute()` |
| Agent model operation | Operation span | Request, candidate, validated response, usage | Model adapter, Agent, or containing flow |
| Generic provider model operation | Provider span | Raw request/response/usage when present | Historical evaluation first; provider adapter later |
| Junjo Agent Tool operation | Tool operation span | Requested/validated arguments, result, state revision, nested execution | Application Tool adapter or containing Agent |
| Raw span | Trace and span ID | Complete normalized raw evidence and child subtree | Historical evaluation; application adapter when one exists |

### State And Output Evidence

| Entity or projection | Exact anchor | Evaluator-facing meaning |
| --- | --- | --- |
| Store | Trace and Store ID | Complete Store annotation, boundaries, transition timeline, and integrity |
| Store transition | Trace, Store ID, sequence, source span/event | Before state, patch, after state |
| Store state boundary | Trace, Store ID, start/end/before-transition sequence/after-transition sequence | Complete state plus payload and integrity status |
| Workflow/Subflow output | Owning executable plus `store.end` projection | Final detached state or selected field |
| Node output | Node plus directly attributable transition or proven boundary projection | Node effect; Nodes do not have a hidden return value |
| Agent output | Agent owner output slot | Validated Agent result |
| Model output | Model operation response slot | Candidate or validated response |
| Tool output | Tool operation result slot | Candidate or committed Tool result |
| Image or other artifact | Producing entity plus payload/reference slot | Full payload or emitted artifact reference according to telemetry policy |

Generic external Tool, evaluator, verifier, and provider instrumentation uses
the raw-span entity until an accepted normalizer gives it stronger semantics.

Evaluation orchestrator, subject, judge, verifier, dataset-generator, and result
evidence are roles over these same entity types. A role boundary is required in
evaluation evidence so a judge model operation or verifier Tool span cannot be
mistaken for a subject member or included in subject usage.

Output is a projection of its producing entity, not an unrelated globally
addressed object. Payload evidence and integrity remain attached. Emitted
`full`, `redacted`, `reference`, and `excluded` modes stay distinct, and
Studio's `missing` diagnostic must not be misrepresented as an emitted payload
mode or empty value.

## Case Membership And Causal Scope

A case contains user-defined named members rather than a rigid fixed tuple:

```json
{
  "caseId": "local-place-001",
  "origin": "generated_evidence",
  "members": [
    {
      "label": "input",
      "source": {
        "kind": "evidence_ref",
        "traceId": "...",
        "spanId": "workflow-owner-span"
      },
      "projection": "workflow.state.start"
    },
    {
      "label": "baseline_answer",
      "source": {
        "kind": "evidence_ref",
        "traceId": "...",
        "spanId": "date-node-span"
      },
      "projection": "node.state.after.response"
    },
    {
      "label": "baseline_complete_flow",
      "source": {
        "kind": "evidence_ref",
        "traceId": "...",
        "spanId": "workflow-owner-span"
      },
      "projection": "subtree"
    }
  ],
  "focalEntity": {
    "traceId": "...",
    "spanId": "date-model-operation"
  },
  "comparisonScopeRoot": {
    "traceId": "...",
    "spanId": "workflow-owner-span"
  }
}
```

The initial projection set should remain small:

- all received trace evidence;
- execution subtree;
- known payload slot;
- Store state or transition; and
- bounded JSON Pointer over normalized evidence where no typed projection
  exists.

A generated set must identify subject roots independently from judge and
verifier roots. Its membership is the bounded physical descendant closure and
verified nested-executable relationships from those roots, not every span that
happens to share an evaluation trace.

For cross-trace execution, the generated set may have multiple subject roots
declared by the capture or runner. Preserved OpenTelemetry links remain
inspectable evidence but do not automatically add another trace to dataset
membership. Generic links have no governed causal-membership semantics today.
Root count, traversal depth, entity count, and response bytes must be bounded.

## Fingerprint Model

Fingerprints explain exactly what stayed equal or changed. They complement the
complete payload evidence; they never replace it.

This section defines the target identity model and the questions each
fingerprint would answer. Horizon 3 adopts it incrementally from the corpus; it
does not make a generalized schema registry, prompt framework, or complete
candidate manifest a prerequisite for the first labeled runner.

### Common Portable Rule

Every new portable artifact identity should use:

```text
<kind>_sha256:<64 lowercase hexadecimal characters>
  = SHA-256(RFC-8785(canonical portable I-JSON material))
```

Every material shape includes an explicit version. It excludes credentials,
mutable clients, runtime IDs, dataset IDs, experiment IDs, timestamps, and
environment. Arrays preserve order only when order changes behavior.

Fingerprints establish content equality. They are not authorization, secrecy,
source attestation, or a claim that two different JSON Schemas are
mathematically equivalent.

### Existing Structural Identity

Existing identity remains useful:

- Agent structural identity already includes exact instructions, normalized
  input and output schemas, model descriptor and settings, ordered Tools,
  limits, and Agent key.
- Tool structural identity already includes Tool name, description, and
  normalized input and output schemas.
- Workflow Graph, Node, and edge structural IDs describe topology, labels,
  position, concurrency, and nested Subflow shape.

Existing Workflow and Node structural IDs do not include state schema, prompt
content, Node configuration or implementation, model settings, or application
source. They remain Studio mapping and comparison evidence but are not a
complete candidate fingerprint. They also are not instances of the new
portable fingerprint rule: current Graph code uses deterministic Python JSON,
truncates SHA-256 to 128 bits, and includes Python class names, labels,
declaration order, concurrency membership, nested Graph IDs, and condition
strings.

### State-Schema Fingerprint

Workflow and Subflow dataset evidence needs the exact shape of the state it was
built against.

The proposed v1 material contains:

```json
{
  "v": 1,
  "validationSchema": {},
  "evidenceSchema": {}
}
```

The proposal reuses the existing Agent generated-schema normalization profile
where it applies, but the current private Agent helper cannot be used unchanged:
it requires validation and serialization schemas to be equal. Workflow state
validation and evidence schemas must be generated and normalized separately.
They remain separate even when equal because runtime validation and telemetry
serialization are different responsibilities.

The resulting identity is:

```text
state_schema_sha256:<digest>
```

Workflow and Subflow owner evidence should carry the ID. Studio should retain
the normalized schema material once as evaluation artifact metadata rather than
repeating it on every span. This is not Horizon 5's general user-defined schema
registry. A Node case inherits the state-schema identity from its enclosing
Store owner.

A schema mismatch is not silently coerced during case execution. The runner
either:

- executes against the exact required schema;
- creates a new authored case or dataset version with explicitly transformed
  input; or
- reports the case as incompatible with the candidate.

This fingerprint identifies generated schema shapes. It does not fingerprint
custom validators, serializers, migrations, or complete runtime behavior. The
first implementation should reuse the proven Agent normalization rules rather
than inventing an unrelated profile, but only after Workflow state behavior is
proven against those rules.

### Prompt-Template Fingerprints

The rendered prompt alone cannot reveal the template that produced it.
Horizon 3 therefore needs explicit provider-neutral prompt artifact evidence at
the application model-call boundary.

The target representation is an ordered message/part structure with:

- stable application-owned prompt key;
- role and part ordering;
- exact literal text;
- named variable parts;
- variable encoding;
- input schema identity; and
- an explicit artifact-material version.

Three identities answer different questions:

1. `prompt_shape_sha256`

   Hashes roles, part ordering, variable names, encodings, and input schema
   while replacing literal text with a literal marker. It identifies the
   template interface and layout.

2. `prompt_content_sha256`

   Hashes the complete template, including exact literal text. Wording,
   punctuation, whitespace, or variable-contract changes produce a new ID.

3. `prompt_instance_sha256`

   Hashes the fully rendered provider-neutral prompt together with its content
   ID. It identifies the exact case-specific prompt instance.

Junjo Agent model requests already have a governed normalized request payload.
Workflow model-call evidence is provider-specific today and may not expose the
same complete request. Future redacted, reference, or excluded evidence also
may not contain inline prompt content. Reusable template material, if the
vertical proof demonstrates that Studio must retain it, belongs in bounded
evaluation artifact metadata and is not repeated as flat attributes.

AI Chat prompt functions currently return ordinary f-strings. Template shape
and content cannot be inferred reliably from them. The local-place vertical
slice should prove the smallest explicit prompt-artifact boundary before Junjo
standardizes a general public prompt abstraction.

AI Chat's date response currently uses the shared
`persona_response_prompt()` template and injects a date-specific static
directive string alongside case-specific profile, history, and user-message
values. Its artifact proof must distinguish candidate-owned static fragments
from case-owned variables; it must not pretend a standalone date template
already exists.

Agent instructions already participate in the Agent structural fingerprint.
A separate prompt/instruction content ID is still useful because it lets Studio
report that instructions changed without treating every field of the aggregate
Agent fingerprint as an opaque difference.

### Candidate Fingerprint

A human label such as `date-prompt-v2` is useful but not sufficient identity.
A candidate is an immutable manifest that may include:

- target kind and application-owned target key;
- implementation artifact identity;
- executable or Graph structural identity;
- state-schema identities;
- prompt shape and content identities keyed by prompt key;
- model bindings and behavior-affecting settings;
- Tool structural identities; and
- behavior-affecting application configuration.

The manifest produces `candidate_sha256:<digest>`.

Dataset, experiment, case, repetition, judge, environment, timestamps, and
credentials remain outside subject candidate identity. Judge candidate identity
is separate so changing the judge never makes the subject appear to have
changed.

The MVP must record service version, source revision, and dirty-worktree status
as provenance. It may begin with a human candidate label, existing structural
IDs, model settings, and exact rendered requests already present in trace
evidence. A stronger implementation artifact digest becomes required before
Junjo claims that a candidate manifest fully identifies arbitrary application
behavior.

## Run Classification And Evaluation Context

Horizon 3 requires three trace-level run classes:

| Run class | Meaning | Default Studio cohort |
| --- | --- | --- |
| `application` | Real application use | Application |
| `dataset_generation` | Deliberate execution used to create dataset evidence | Evaluation development |
| `evaluation` | Candidate, judge, or verifier execution for an evaluation run | Evaluation |

Provisional evaluation context includes:

- capture ID for dataset-generation work;
- experiment and evaluation-run IDs;
- dataset ID and immutable version;
- evaluation-definition version;
- case ID and repetition;
- candidate ID;
- subject kind;
- role: orchestrator, subject, judge, verifier, dataset generator, or result;
  and
- exact subject root identity when available.

`ExecutionCorrelation` remains the application-domain identity defined by ADR
0007. Horizon 3 must not overload a Turn correlation with dataset, experiment,
candidate, and judge identity.

The first discovery slice should use one explicit outer OpenTelemetry span and
a dedicated evaluation process whose immutable Resource may carry a
process-level marker. The outer case span carries per-case class, capture,
dataset, and case identity and acts as the orchestrator. Explicit
application-owned child boundary spans identify the subject, judge, and
verifier branches and carry their respective candidate identities. A mixed
application/evaluation process cannot classify individual cases through
Resource attributes alone. This proves whether trace-level classification,
physical parentage, role boundaries, and subject-root identity are sufficient
for all Junjo and provider spans.

Before shared implementation, the evaluation ADR must decide whether the
proven context belongs only on the evaluation root, on every Junjo semantic
span, or in a fixed SDK execution context. A public propagation contract should
not be invented until the labeled corpus demonstrates the failure of the
simpler root model.

Studio presents explicit Application, Dataset Generation, Evaluation, and All
views. All received raw trace evidence remains inspectable in every class.

## Evaluation Trace Shape

Each case attempt should remain one bounded trace where possible:

```text
evaluation case root
  -> subject role boundary
       -> subject execution root
            -> real Node / Agent / Workflow evidence
            -> downstream model, Tool, state, and nested executable evidence
  -> evaluator role boundary
       -> deterministic evaluator
  -> verifier role boundary
       -> external verifier
  -> judge role boundary
       -> model judge
  -> result role boundary
       -> result evidence
```

Subject cost, latency, and usage exclude evaluator, verifier, and judge work.
Historical-only evaluation creates a new evaluation trace linked to the
historical subject rather than reclassifying the original application trace.
If asynchronous or cross-process work escapes these physical boundaries, the
evaluation-context ADR must define the minimum trusted role propagation rather
than infer role from span names.

## Studio Ownership And Storage

Studio owns:

- dataset drafts and immutable versions;
- exact evidence anchors, projections, and resolved entity manifests;
- evaluation-definition metadata;
- candidate manifests and artifact metadata;
- experiments, evaluation-run lifecycle, case outcomes, and comparisons;
- semantic evidence queries and compact subject projections; and
- links to all received canonical trace evidence.

Full trace evidence remains in the current hot/cold Parquet path. Small
canonical control-plane records belong in `junjo.db` or another explicitly
accepted canonical store. Rebuildable trace/file locator facets belong in
`metadata.db`. Dataset versions, literal values, evaluation definitions,
candidate metadata, and results must never be placed in the rebuildable
metadata database. The Studio ADR must measure canonical write contention,
including interaction with API-key validation, before choosing whether to
share `junjo.db` or add another canonical store. Studio must not create a
relational copy of complete spans, prompts, state, or conversations.

The first dataset API needs only:

- create and update a dataset draft;
- add authored literal cases;
- start and resolve a dataset-generation capture;
- add exact historical evidence references;
- inspect the resolved entity manifest;
- freeze an immutable dataset version;
- retrieve ordered cases and their compact projections; and
- retrieve complete `TraceEvidence` on demand.

The MVP begins with exact IDs and explicit references. A broad saved-query DSL,
automatic cohorts, and arbitrary semantic filters follow only after the
vertical slice establishes the necessary selection fields.

Immutable cohort materialization later requires a fixed query snapshot or
watermark, stable ordering and cursor keys, explicit continuation/completion
status, bounded service/time/file windows, and deterministic hot/recent-cold/
cold deduplication. It must never silently inherit a recent-file limit from a
UI-oriented list query.

Compact projections initially reduce response bytes and coding-agent context;
they do not automatically reduce backend scan or assembly work. Dataset
hydration should return references by default, group requested members by
trace, bound hydrated traces per request, and add projection-specific
DataFusion filters only where measured. It must not perform one complete trace
query and hot-snapshot preparation per member or add a default in-memory
full-trace cache.

Programmatic Studio access is an API concern, not an import workflow. A coding
agent uses a Studio programmatic credential to query evidence and manage
datasets or evaluations. Existing browser sessions remain a human UI
mechanism, and OTLP ingestion remains an ingestion boundary.

## Harness Ownership

Studio cannot instantiate arbitrary application dependencies from telemetry.
The application-side runner owns:

- decoding a dataset case into executable input or state;
- constructing the selected candidate's providers, dependencies, Stores,
  Nodes, Agents, Workflows, and application services;
- executing through Junjo's supported public lifecycle;
- projecting subject output for evaluators;
- running application-selected evaluators; and
- exporting supported evaluation telemetry.

The first implementation should be an explicit AI Chat runner, not a
generalized plugin framework. After both a Node re-execution and a complete
Workflow re-execution work, Junjo may extract only the common public protocols
demonstrated by real repetition.

Potential later protocols include a dataset provider, target runner, evaluator,
result recorder, and Studio adapter. Their names and package ownership remain
open until the vertical proof.

## Coding-Agent Interface

The semantic REST API is the source contract. A typed Python client and CLI
provide ordinary developer ergonomics. MCP, added later within Horizon 3, is a
thin adapter over the same operations.

A coding agent should ultimately be able to:

1. search bounded application, dataset-generation, or evaluation evidence;
2. retrieve all received trace evidence or compact
   executable/model/state projections;
3. create a dataset draft;
4. add historical, authored, or deliberately generated cases;
5. inspect and freeze a dataset version;
6. retrieve a dataset and evaluation definition;
7. create an experiment and candidate run;
8. execute application-owned targets and evaluators;
9. query missing, failed, regressed, and improved cases;
10. retrieve paired subject evidence and trace differences; and
11. repeat the loop with a new candidate.

Compact projections exist for query cost and coding-agent context efficiency.
They are views over canonical received evidence, never substitutes for it.

## Iterative MVP Sequence

Horizon 3 follows a corpus-first, contracts-second implementation strategy.
Each slice must produce inspectable evidence and answer a decision gate before
the next shared abstraction is accepted.

### H3.1: Labeled Evidence Corpus

Use current public execution paths to generate a small deliberate AI Chat
corpus:

- directive-selection Node cases through `evaluate_node()`;
- date-response Node cases;
- direct Agent cases covering no Tool, history Tool, and image Workflow Tool;
- complete Turn Workflow cases covering directive selection and downstream
  branches; and
- approximately 8–12 local-place realism cases.

Run the current baseline and one prompt-only candidate. Wrap each case in an
application-owned evaluation root span and run it from a dedicated evaluation
process/resource. This discovery slice must not change the shared Junjo
telemetry contract.

Exit evidence:

- case traces are received in Studio with explicit readiness and integrity
  status;
- application correlation remains truthful;
- dataset-generation/evaluation traces are distinguishable from application
  traces;
- explicit subject, judge, and verifier role boundaries and their roots can be
  identified;
- Node and Workflow state input/output can be reconstructed; and
- cross-trace or escaped-provider-span behavior is documented.

Decision gate:

- Is root-span and resource classification sufficient, or does the SDK require
  fixed evaluation-context propagation?

### H3.2: Two Concrete Dataset Shapes

Model two immutable dataset versions from the corpus using explicit
application-owned manifests and current Studio trace retrieval. This is a
contract prototype, not the permanent Studio persistence or API
implementation.

Entity dataset:

- exact date-response Node anchor;
- provisional state-schema material and identity clearly marked as
  non-contractual;
- directly attributable Node Store transitions and entry/exit state only where
  the corpus proves those boundaries;
- selected answer projection;
- prompt/model child evidence; and
- explicit expected constraints.

End-to-end dataset:

- exact Turn Workflow subject root;
- starting state/input;
- selected path;
- final state/response;
- every downstream executable and operation in the bounded generated closure;
  and
- focal prompt/model entity plus complete comparison scope root.

Also add at least one literal authored case that has never run before, execute
it directly through application code, and attach the resulting generated
evidence set.

The first implementation uses explicit anchors and projections rather than a
general query language. Any provisional state or prompt fingerprints used in
this discovery artifact are clearly marked non-contractual until H3.3 accepts
their canonical material.

Decision gates:

- Can Studio reconstruct entity input and output without ambiguity?
- What dependencies are missing from telemetry and must be supplied by the
  AI Chat runner?
- Which descendants should be separate dataset cases versus attached evidence
  members?
- Can Node and RunConcurrent Store boundaries be derived exactly, or does the
  telemetry contract need explicit boundary evidence?
- When is trace evidence complete enough to freeze subject roots and named
  members?

### H3.3: Accept Minimum Evaluation Contracts And Fingerprint Slice

Use H3.1 and H3.2 evidence to accept:

- evaluation run classification and context;
- generated evidence set and subject-root semantics;
- dataset case, anchor, projection, membership-rule, and optional bounded
  manifest contracts;
- minimum candidate provenance;
- result authority and reconciliation semantics; and
- Studio control metadata versus rebuildable evidence-index ownership.

State-schema identity is an explicit Horizon 3 requirement. H3.3 accepts the
smallest state-schema fingerprint proven by the entity and end-to-end corpus;
H3.2's provisional value does not become contractual by accident.

Prompt-template shape identity is a proposed Horizon 3 capability rather than a
precondition for the first runner. Start from current structural identities,
service/source provenance, model settings, exact rendered request evidence
where available, and explicit AI Chat prompt-fragment provenance. Accept
prompt-content, prompt-shape, prompt-instance, or stronger candidate
fingerprints only when the corpus demonstrates that identity's comparison
value and the application boundary can produce it truthfully.

Only after acceptance should the SDK and shared telemetry contract change.

Exit evidence:

- canonical cross-language fixtures for every fingerprint actually accepted in
  this slice;
- SDK producer and Studio consumer conformance fixtures;
- documented payload, artifact, and index ownership; and
- an explicit decision on telemetry contract versioning.

### H3.4: Minimal Dataset API And AI Chat Runner

Implement the smallest programmatic loop:

1. retrieve one immutable dataset version;
2. construct fresh AI Chat dependencies;
3. execute the date-response Node through `evaluate_node()`;
4. execute the complete Turn Workflow without starting FastAPI or the
   frontend;
5. label the candidate execution;
6. run deterministic and qualitative evaluators; and
7. link every case outcome to all received Studio evidence.

This slice also ships the minimum run-class index/filter and default
Application, Dataset Generation, and Evaluation views. A released runner must
not pollute ordinary application views while richer experiment grouping is
still under construction.

Do not introduce a plugin registry, evaluator DSL, generalized re-execution
engine, or cross-language harness in this slice.

Exit evidence:

- one command runs both entity and end-to-end cases;
- every case attempt has an explicit execution outcome;
- every case attempt has independent telemetry readiness and integrity status;
- the subject root is exact when execution started and explicitly absent when
  setup or admission failed before the Junjo subject span existed;
- authored and historical cases share one runner boundary; and
- the same dataset version runs against baseline and candidate.

### H3.5: Evaluation Tracking And Siloing

Add Studio experiment, evaluation-run, candidate, case-attempt, and result
queries. Preserve distinct subject, judge, and verifier evidence.

Implement the result authority accepted in H3.3. If the control-plane record is
canonical, telemetry is linked execution evidence. If telemetry is canonical,
the query record is explicitly a rebuildable projection. Do not create two
authoritative result channels.

Exit evidence:

- application views exclude dataset-generation and evaluation traffic by
  default;
- evaluation views group cases by dataset version, candidate, and repetition;
- subject usage and latency exclude judge/verifier work;
- missing telemetry is visible rather than fabricated as a result; and
- coding agents can query outcomes without reading local result files.

### H3.6: First Useful Comparison

Ship a paired case comparison for the local-place dataset:

- baseline and candidate criteria;
- pass, score, and reason deltas;
- verified-place and constraint deltas;
- subject latency, usage, and Tool-call deltas;
- runtime, provider, evaluator, and telemetry-integrity failures;
- prompt, schema, model, executable, and candidate provenance plus every
  accepted fingerprint difference;
- links to all received evidence for both traces; and
- side-by-side execution trees with unmatched evidence explicit.

Begin with deterministic pairing by dataset case. Prototype alignment using
existing Graph/Node structural IDs, Agent keys, semantic parentage, operation
sequence, and Store revision order. Add another stable executable-key contract
only if the real corpus proves existing evidence insufficient.

The first version may identify the first changed model request, state
transition, or branch without building a universal semantic trace-diff engine.

### H3.7: Generalize The Proven Loop

After the local-place vertical proof:

- extract the smallest reusable harness protocols;
- add bounded evidence search and saved selections;
- materialize historical cohorts into immutable dataset versions;
- expand target support across Agent, Workflow, Subflow, model, and Tool
  operations;
- add additional evaluation-definition types;
- add typed Python and CLI conveniences;
- expose the stable contract through MCP; and
- add richer aggregate and repeated-run comparison.

Horizon 4 then builds autonomous cohort discovery, improvement proposals, and
governed agent-led iteration on these stable primitives. Basic agent access to
datasets and evaluation evidence is part of Horizon 3.

## AI Chat Local-Place Realism Vertical Proof

The current shared persona-response template receives a date-specific directive
asking for real places, while its evaluation only establishes plausibility.
Horizon 3's first vertical proof must measure authenticity.

### Dataset Construction

Create cases through all three origins:

- historical date-response traces;
- deliberately generated full Turn Workflow traces; and
- literal authored inputs that have never been run.

Case dimensions include:

- dense city, suburb, small town, and rural geography;
- exact neighborhood and radius constraints;
- walking, public-transit, and driving constraints;
- budget and price level;
- indoor/outdoor and weather constraints;
- accessibility;
- alcohol-free and dietary preferences;
- specific day/time and current operating status;
- contact interests and prior conversation preferences;
- ambiguous or missing location where clarification is correct; and
- closed, renamed, nonexistent, wrong-city, generic, or overly distant places.

### Evaluator Layers

Evaluate separately:

1. structured place-claim extraction;
2. real entity and stable place-ID verification;
3. coordinates, distance, category, and geographic fit;
4. opening-status and time fit using timestamped evidence;
5. explicit user-constraint satisfaction;
6. persona and prior-context fit; and
7. conversational specificity and realism.

Existence, identity, distance, and explicit constraints should be deterministic
or grounded in a declared place-data source. A model judge evaluates qualitative
persona and conversational dimensions; it does not establish that a venue
exists.

The verifier provider, timestamp, source identity, coordinates, facts, and
version belong in verifier evidence. Baseline and candidate use the same
dataset, verifier, evaluator definition, and close execution window.

### Candidate Sequence

Compare:

1. the current prompt-only baseline;
2. one prompt-only improvement; and
3. a grounded place-search candidate only if measured evidence justifies the
   added Tool or Workflow capability.

Run the isolated date-response Node for fast prompt iteration and the complete
Turn Workflow to measure directive selection, state, branching, persistence,
and every downstream effect.

### Vertical-Proof Exit Criteria

- A coding agent can create or retrieve the local-place dataset version.
- The dataset contains both focused Node cases and complete Workflow cases.
- A deliberately generated Workflow run contributes its complete labeled
  subject closure and named entity members.
- Every case records state-schema and prompt/candidate fingerprints where the
  contract supports them.
- Baseline and candidate executions appear only in evaluation cohorts by
  default.
- Studio shows all received subject trace evidence, its integrity status, and
  separate judge/verifier evidence.
- The comparison identifies quality, authenticity, constraint, latency, usage,
  and causal execution differences.
- Evidence determines whether a prompt change is sufficient or a place-search
  capability is warranted.

## Low-Resource Architecture Rules

Horizon 3 must preserve Studio's small-host priorities:

- no synchronous dataset or evaluation work in the Rust OTLP ingestion hot
  path;
- no duplicate trace-payload store;
- full evidence remains in Parquet;
- SQLite contains bounded control records and rebuildable trace/file locator
  facets in their correct canonical or rebuildable database, not a generic
  per-span semantic copy;
- DataFusion performs final evidence filtering after bounded file selection;
- initial dataset construction uses exact IDs before a broad query language;
- list/search APIs require bounds and cursor pagination;
- compact projections avoid forcing coding agents to load full traces when they
  need one entity, while backend scan/assembly savings are measured separately;
- all received trace evidence remains available on demand;
- dataset hydration groups members by trace and bounds hydrated traces,
  projection bytes, and closure traversal;
- one case attempt remains independently bounded;
- harness concurrency defaults conservatively and is explicitly configurable;
  and
- dataset, comparison, and mixed-cohort work is benchmarked on the supported
  one-vCPU/1GB profile.

Before accepting a new index or query strategy, record baseline and candidate:

- OTLP ingestion throughput;
- peak and steady-state ingestion RSS;
- backend RSS;
- hot, recent-cold, and cold query p50/p95;
- dataset materialization duration;
- comparison duration; and
- database and Parquet storage growth.

Hard limits must cover literal bytes, members per case, cases per version,
optional manifest bytes, artifact bytes, subject-root count, closure depth and
entity count, hydrated traces per request, and projection response bytes.

Performance thresholds must be set from measured baselines. The plan must not
guess acceptable regressions after implementation.

## ADR Plan

After the H3.1/H3.2 discovery corpus and before shared contract implementation:

1. Write a root ADR for Studio-native datasets, generated evidence sets,
   evaluation ownership, application-executed targets, and open evaluators.
2. Write or incorporate a root telemetry decision for run classification,
   evaluation context, subject roots, roles, state/prompt/candidate
   fingerprints, and contract versioning.
3. Write a Studio ADR for dataset and experiment persistence, exact evidence
   references, entity projections, query/index boundaries, retention behavior,
   pagination, programmatic authentication, and low-resource budgets.
4. Clarify ADR 0010: its faithful `evaluate_node()` execution decision remains;
   Horizon 3 activates the later evidence-plane capability that owns datasets
   and experiments.
5. Clarify Studio ADR 007: complete Agent evidence remains the foundation;
   Horizon 3 resolves its deferred dataset, experiment, replay, and
   programmatic-access decisions.
6. Keep application correlation from ADR 0007 distinct from evaluation
   identity.

## Validation Strategy

Every shared implementation slice must validate all affected owners.

At minimum:

- shared telemetry schemas, canonical fixtures, deterministic regeneration,
  producer conformance, and Studio consumer conformance;
- Python SDK Ruff, pytest, ty, public-surface validation, package build, and
  Twine validation;
- full Studio backend, frontend, ingestion, and contract tests;
- Compose E2E execution from AI Chat through ingestion and Studio;
- exact entity selection and payload/integrity preservation;
- application/dataset-generation/evaluation cohort isolation;
- Node, Agent, Workflow, nested Workflow/Agent, and failed-run evidence;
- repeatable dataset fingerprint and candidate pairing;
- live local-place evaluation with explicit credentials; and
- one-vCPU/1GB ingestion, memory, query, and comparison benchmarks.

Probabilistic quality does not become a default deterministic CI gate. The
mechanics, contracts, identities, isolation, and fixture results remain
deterministic CI responsibilities.

## Open Decisions

The following questions remain intentionally open until the vertical evidence
answers them:

- Is evaluation-root classification enough, or must fixed context be repeated
  on every Junjo semantic span?
- How should context cross asynchronous or network boundaries without treating
  untrusted baggage as authoritative identity?
- When is a trace complete enough to freeze generated subject roots and named
  members?
- Should a frozen dataset pin referenced evidence, preserve a bounded replay
  fixture, or report missing evidence after future retention?
- Which Node projections are reusable input/output versus application-specific
  state fields?
- Does Studio need a normalized generic provider model-operation contract after
  the Agent model-operation proof?
- What is the smallest explicit prompt-artifact API that works for ordinary
  Workflow Nodes without turning Junjo into a provider SDK?
- Is the existing Agent schema normalization profile sufficient for Workflow
  state validation and evidence schemas?
- What application artifact digest can truthfully identify arbitrary Node,
  Workflow, Subflow, and Tool implementation behavior?
- Are current Graph, Node, Agent, parent, and operation identities sufficient
  for prompt-only trace alignment?
- Should experiment run state be API-owned while result evidence is
  telemetry-owned, or is one idempotent result-write contract required?
- Which evaluation-definition fields belong in Studio and which remain solely
  in application code?
- Which place-data provider offers acceptable coverage, freshness, licensing,
  latency, and cost?
- What programmatic credential model is sufficient without creating a separate
  identity system?
- What measured query and concurrency limits remain safe on one vCPU/1GB?

## Working Decision Record

| Date | Status | Decision |
| --- | --- | --- |
| 2026-07-27 | Direction accepted for planning | Studio's existing received trace evidence is canonical; no bundle or browser-upload workflow is part of Horizon 3. |
| 2026-07-27 | Direction accepted for planning | Dataset cases may come from historical evidence, literal programmatic authoring, or deliberate real executions labeled as dataset generation. |
| 2026-07-27 | Direction accepted for planning | A generated Agent or Workflow run contributes complete flow evidence, while every executed entity remains individually addressable for focused datasets. |
| 2026-07-27 | Direction accepted for planning | A case separates its focal entity from its wider comparison scope root so upstream prompt changes can be measured through all downstream effects. |
| 2026-07-27 | Direction accepted; material proposed | Dataset cases require state-schema shape identity; exact hash material depends on corpus evidence and ADR acceptance. |
| 2026-07-27 | Proposed; requires corpus proof | Prompt-template shape/content/instance fingerprints should replace handwritten labels only where an explicit prompt artifact boundary can produce them truthfully. |
| 2026-07-27 | Direction accepted for planning | Dataset-generation and evaluation traces are distinct from real application traffic while retaining the same canonical telemetry storage path. |
| 2026-07-27 | Proposed; requires corpus proof and ADR | Use a root evaluation span first, then add SDK evaluation-context propagation only if real traces prove it necessary. |
| 2026-07-27 | Proposed; requires implementation proof | Build one AI Chat Node plus complete Workflow vertical slice before extracting a generalized harness or broad semantic query system. |

Update this record as decisions are accepted, rejected, or replaced. Do not
silently turn a proposed item into an implemented contract.
