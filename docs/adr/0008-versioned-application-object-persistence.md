# ADR 0008: Versioned application object persistence

- Status: Accepted
- Date: 2026-07-14
- Owners: Junjo platform

## Context

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

## Decision

### Canonical application data is a versioned object

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

### Canonical objects and projections have different ownership

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

### Application ports hide physical persistence, not domain semantics

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

### Model context is a governed projection

Applications never dump an arbitrary object store into a model request.
Context assembly selects schema-aware projections under an explicit,
versioned policy with deterministic ordering and size limits. Conditional or
large retrieval remains an Agent Tool; context required on every execution is
prepared by the deterministic Workflow or application boundary.

### AI Chat is the first bounded Turn-object proof

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
Message responses are projections of Turn objects. This proves the logical
contract without prematurely selecting the permanent object-storage system.

## Consequences

User-defined data can evolve through explicit schema and object revisions while
deterministic indexes remain available for exact queries. LLM context becomes
a deliberate application product instead of an accidental database dump.

The platform must eventually provide a schema registry, transformation
records, projection rebuilds, and object-level authorization. AI Chat proves
only the bounded Turn contract and adapter boundary; it is not the complete
Horizon 5 substrate.

## Rejected alternatives

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
