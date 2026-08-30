# ADR 0008: Versioned application object persistence

- Status: Amended; bounded AI Chat Turn accepted, generalized object/schema
  substrate withdrawn
- Date: 2026-07-14
- Amended: 2026-08-30 (generalized substrate withdrawn and Horizon 5 cancelled)
- Owners: Junjo platform

## 2026-08-30 amendment

The generalized versioned-object and schema substrate in this ADR is no longer
an accepted Junjo platform direction. It prescribed a schema registry,
immutable application-object revisions, transformations, projections, and
object authorization before a concrete MBB product story demonstrated that
runtime user-defined tracker types were required. It is not needed for Junjo's
execution kernel, Studio evaluation and evidence, or the Git-based
coding-agent improvement loop.

Applications own their domain models, repositories, database schemas,
migrations, authorization, and durable product data. Junjo continues to
execute and observe application-owned capabilities through narrow Node and
Tool boundaries, while Studio retains execution and evaluation evidence.

AI Chat's fixed, application-owned Turn aggregate remains an implemented and
useful domain design. Its server-owned identity, lifecycle, typed JSON, and
execution references do not establish a need for a generalized persistence
platform. Any future runtime-defined MBB tracker must start from a concrete
application-owned user story and a new accepted decision.

The generalized material below records the withdrawn historical proposal and
is not normative. The bounded AI Chat Turn decision and the application-owned
port boundaries remain accepted.

## Historical context

The long-term product direction requires user-defined tracked concepts,
schemas, processing behavior, and views to evolve without making relational
DDL the product-definition boundary. AI systems must be able to inspect
portable data and schemas, while deterministic machinery continues to own
validation, identity, ordering, concurrency, indexing, authorization, and
external side effects.

Object-stored JSON improves payload evolution, but an object store alone does
not provide application invariants, atomic admission, efficient queries,
cross-object transactions, search, or bounded model context. Treating all JSON
as model context would also collapse persistence, retrieval, and prompt policy.

This decision establishes the logical persistence direction. It does not pick
a permanent object-storage vendor or require every current application table
to move before the model is proven.

## Amended decision

### Withdrawn generalized canonical-object direction

The following records the former, non-normative direction.

A canonical object is a portable JSON document with an immutable object type,
schema version, server-owned identity, revision, provenance, lifecycle data,
and typed payload. The schema version defines the data. It is separate from:

- the object revision;
- the producing code or service version;
- Junjo definition and structural identities;
- Junjo runtime identities; and
- context-policy and evaluation versions.

Schemas are immutable once accepted. A semantic change creates a new schema
version. Historical objects retain their original schema identity. Explicit
transformations produce a new revision or object; readers do not silently
reinterpret old data as a newer schema.

### Withdrawn generalized object-and-projection direction

The following records the former, non-normative direction.

Canonical objects are the durable source for product data. Relational,
analytical, full-text, graph, semantic, and vector structures are rebuildable
projections chosen for deterministic query needs.

Projection schemas may still change. The objective is not to eliminate every
database migration; it is to prevent projection DDL from becoming the
definition of user-facing product data or forcing canonical historical payload
rewrites.

Large binary artifacts are stored separately and referenced by durable
identity and integrity material. Telemetry remains in the Studio evidence
plane and is referenced by execution identity rather than copied into product
objects.

### Retained application-port boundary

Workflows, Nodes, Agents, and Tools consume narrow application-owned ports.
They do not receive raw object-store, SQL, search, or vector credentials.

The persistence adapter owns:

- schema validation at write and read boundaries;
- atomic revision and lifecycle transitions;
- optimistic concurrency or stronger application invariants;
- canonical serialization and integrity fingerprints where required; and
- projection updates or durable projection work records.

The domain owns valid transitions and object meaning. The adapter does not
invent lifecycle semantics from JSON fields.

### Retained model-context boundary

Applications never dump an arbitrary object store into a model request.
Context assembly selects schema-aware projections under an explicit,
versioned policy with deterministic ordering and size limits. Conditional or
large retrieval remains an Agent Tool; context required on every execution is
prepared by the deterministic Workflow or application boundary.

### Retained bounded AI Chat Turn decision

AI Chat replaces implicit message pairing with one server-created,
schema-versioned Turn object. A Turn owns:

- conversation sequence and lifecycle status;
- accepted user input;
- optional assistant result;
- failure or cancellation outcome;
- context-policy identity; and
- durable Workflow and Agent execution references.

SQLite is the first adapter and stores the canonical Turn JSON document plus
only the identity and ordering fields required to locate it deterministically.
Message responses are projections of Turn objects. This proves the bounded
application contract without selecting or requiring a generalized Junjo
object-storage system.

## Historical consequences

User-defined data can evolve through explicit schema and object revisions while
deterministic indexes remain available for exact queries. LLM context becomes
a deliberate application product instead of an accidental database dump.

Under the former direction, the platform would eventually have provided a
schema registry, transformation records, projection rebuilds, and object-level
authorization. AI Chat proved only the bounded Turn contract and adapter
boundary; it did not prove the generalized substrate.

## Alternatives rejected by the former decision

- Arbitrary per-user SQL DDL: it makes physical projection shape the product
  definition and creates unbounded migration machinery.
- JSON blob with no schema identity: historical interpretation and validation
  become implicit.
- Schema version equal to deployment version: unrelated code releases create
  false data versions and obscure semantic changes.
- Object storage as the only query engine: exact filtering, ordering,
  authorization, and large relationship traversal still need deterministic
  machinery.
- Copy full telemetry into objects: product data and diagnostic evidence have
  different retention, access, and query responsibilities.
- Give Agents raw persistence credentials: it bypasses application invariants
  and makes side effects unobservable policy decisions.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0007: Application execution correlation and Studio resolution](0007-execution-correlation-and-studio-resolution.md)
- [Agent layer roadmap](../roadmaps/AGENT_LAYER_ROADMAP.md)
