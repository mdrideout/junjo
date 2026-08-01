# ADR-002: Redux Toolkit Listener Middleware Pattern

## Status

Accepted

## Context

The frontend needs one durable pattern for:

- deciding where state belongs
- async side effects
- state transitions
- derived state
- request boundaries
- runtime schema validation
- component/store separation of concerns

The repo already uses Redux Toolkit. We want a pattern that stays simpler than sagas, more explicit than ad hoc thunks, and easy to test feature-by-feature.

The separation of concerns and file roles are part of the architecture decision here, not incidental foldering. This ADR intentionally documents those boundaries.

## Decision

Use Redux Toolkit listener middleware as the default async orchestration pattern for frontend feature state.

This does not mean all state or all asynchronous work belongs in Redux. State
ownership is chosen first; the Redux rules apply after a concern genuinely
belongs to the application store.

### State Ownership

Place state at the narrowest ownership boundary that can represent it
correctly. Make that choice from the behavior of the feature rather than from
the name of a UI element or a fixed component-depth rule.

Evaluate these factors together:

- **Semantic ownership:** which feature or component is responsible for the
  meaning of the value?
- **Consumer relationship:** are the readers and writers in one cohesive
  subtree, or spread across unrelated branches and features?
- **Lifetime:** should the value disappear with its owning view, survive a
  subtree unmount, or remain authoritative across routes?
- **Source of truth:** is the value local interaction state, navigation state,
  shared application state, or a projection of remote data?
- **Coordination:** must several independently rendered consumers preserve the
  same invariants or react to the same transitions?
- **Prop-passing cost:** do props still express an understandable parent-child
  contract, or are unrelated intermediate components only forwarding values
  and callbacks they do not own?
- **Operational value:** would centralized transitions materially improve
  request reuse, deduplication, debugging, or traceability?

Start with local ownership and explicit props while they keep the data flow
clear. Lift state to the nearest meaningful common owner when nearby consumers
need to coordinate. Use Redux when broader lifetime, fan-out, coordination, or
observability makes application-level ownership simpler than the local design.
There is no prescribed number of component levels after which props become
wrong.

Navigation identity and state intended to be URL-addressable or bookmarkable
should have one explicit authority, commonly the router. React Context remains
appropriate for low-churn, tree-wide infrastructure or capabilities. Neither
Context nor a custom hook should become an implicit second feature store.

Do not represent the same meaningful value independently in local state, URL
state, Context, and Redux unless the synchronization owner and need are
explicit. Duplicate authorities are a stronger warning sign than the choice of
any individual state mechanism.

### Responsibility Split

The frontend uses these ownership rules:

- components own rendering, user interaction, narrow local state, and explicit
  communication with their owning boundary
- hooks own reusable React lifecycle and subscription composition
- slices own shared state shape and synchronous, deterministic reducers
- listener middleware owns consequences of Redux trigger actions, including
  Redux-owned async orchestration and cross-feature effects
- selectors own derived and memoized state
- fetch modules own HTTP request code
- schemas own parsing and runtime contract validation
- utils own pure helpers and typed accessors that do not belong in components or reducers

These boundaries are the normative part of the pattern. New work should preserve them even when file names or folder depth vary.

### Feature Structure

There is a standard feature template, but not every feature needs every file type.

Canonical feature shape:

```text
frontend/src/features/feature-name/
  components/              # Optional feature-local UI components
  hooks/                   # Optional reusable React lifecycle/composition
  store/
    slice.ts               # Required when the feature owns Redux state
    listeners.ts           # Required for Redux-triggered consequences or Redux-owned async orchestration
    selectors.ts           # Required when the feature exposes derived state
  fetch/
    *.ts                   # Optional HTTP request modules
  schemas/
    *.ts                   # Optional Zod/domain/contract schemas
  utils/
    *.ts                   # Optional pure helpers or typed accessors
  FeaturePage.tsx          # Optional entry page/container
```

Allowed small-feature variant:

```text
frontend/src/features/feature-name/
  hooks/                   # Optional
  slice.ts
  listeners.ts             # Conditional; same ownership rule as above
  selectors.ts             # Optional when no derived state is needed
  fetch/
    *.ts
  schemas.ts               # Or response-schemas.ts for small contract surfaces
  *.tsx
```

The repo currently uses both shapes:

- flat small-feature examples:
  - `frontend/src/features/users/`
  - `frontend/src/features/api-keys/`
  - `frontend/src/features/settings/`
- nested store examples:
  - `frontend/src/features/traces/store/`
  - `frontend/src/features/junjo-data/list-spans-workflow/store/`
  - `frontend/src/features/junjo-data/workflow-detail/store/`

### File-Type Rules

#### Slice

- `slice.ts` or `store/slice.ts` defines state and synchronous reducers
- trigger actions may be no-op reducers whose purpose is to be intercepted by listeners
- state-transition actions mutate slice state and are not listener triggers
- a single action type may be a listener trigger or mutate slice state, but
  must not do both
- reducers are pure and deterministic; time, generated identity, and external
  values enter through action payloads
- reducers do not perform fetches, parsing, or unrelated derivation logic

#### Listeners

- `listeners.ts` or `store/listeners.ts` owns consequences of Redux trigger
  actions, including async flows and cross-feature side effects
- listeners call fetch modules, dispatch mutation actions, and read current state when needed
- listener trigger actions do not also mutate slice state; listeners dispatch
  separate state-transition actions as consequences
- synchronous invariants within one slice belong in one reducer, not a chain of
  listener effects or ordinary setter actions
- a listener may dispatch another trigger action when it represents a distinct
  consequence with a clear owner; keep such chains explicit and acyclic rather
  than turning ordinary sequential logic into hidden action pipelines
- listener middleware must be prepended in the root store so it can intercept trigger actions consistently

#### Hooks

- `hooks/*.ts` owns reusable behavior that depends on React lifecycle,
  subscriptions, browser integration, or typed store access
- hooks may compose local state, Context, dispatch, and selectors, but do not
  create a parallel global state layer
- reusable pure Redux derivation belongs in selectors; transport belongs in
  fetch modules
- extract a hook when it creates a clearer ownership boundary or meaningful
  reuse, not merely to move component code into another file

#### Selectors

- `selectors.ts` or `store/selectors.ts` owns derived and memoized state
- expensive or reusable derivation belongs here, not in components
- selectors may compose other selectors across related feature state when needed

#### Fetch Modules

- `fetch/*.ts` owns request construction, `fetch()` calls, and transport-level response handling
- fetch modules do not mutate Redux state directly
- response parsing should happen at the contract boundary through schemas

#### Schemas

- `schemas.ts`, `response-schemas.ts`, or `schemas/*.ts` owns runtime validation and typed domain contracts
- schema modules are the frontend boundary for backend response shape assumptions
- backend contract drift should fail at the schema boundary, not deep inside UI code

#### Utils

- `utils/*.ts` owns pure helpers, transformations, and typed accessor helpers
- utils do not hide side effects or become a parallel state-management layer

#### Components

- components render UI, own appropriately scoped interaction state, pass
  explicit props, select shared state, and dispatch intent actions
- components should not inline transport code, schema parsing, or complex reusable derivation

### Request Ownership

Request state follows the same ownership decision as other state. A request
used only by one mounted owner may remain local. Shared results, lifecycle, or
identity are signals that broader ownership may help, but nearby consumers can
still share a lifted local owner. Use the state-ownership factors above to
decide whether Redux and listener middleware are warranted. Do not move a
request into Redux solely because it is asynchronous.

When request inputs can change before completion, the owner must make the
concurrency policy explicit:

- key independent request state by the identity that makes the results
  distinct; or
- declare the request latest-only and cancel or ignore obsolete results.

A global loading flag must not silently serialize unrelated request
identities. Fetch modules remain responsible for transport and schema parsing
regardless of whether orchestration is local or Redux-owned.

### Query Libraries

Studio does not use RTK Query or TanStack Query. Do not introduce either. The
frontend intentionally keeps request ownership explicit through feature fetch
modules, runtime schemas, local React orchestration where appropriate, and
Redux listener middleware for Redux-owned work.

### Store Registration

At the app level:

- reducers are registered in `frontend/src/root-store/store.ts`
- each feature listener middleware is prepended in `frontend/src/root-store/store.ts`
- typed store hooks remain the default component entry point for dispatch and selection

## Invariants

These are part of the decision:

- state placement is decided by ownership, lifetime, consumer topology, and
  coordination needs rather than UI-element categories or prop-depth quotas
- Redux listener middleware is the default async orchestration mechanism for
  work already owned by Redux
- an action type is a listener trigger or mutates slice state, never both
- listeners own consequences; reducers own synchronous state transitions
- side effects stay out of reducers
- request code stays out of components
- reusable derivation stays out of components when selectors are appropriate
- runtime contract parsing stays explicit at schema boundaries
- RTK Query and TanStack Query are prohibited
- feature structure may vary, but file roles must remain clear

## Consequences

### Positive

- The repo has one default async state pattern.
- State remains local when broader ownership would add more coordination than
  it removes.
- Side effects stay separate from reducers and UI.
- File roles stay explicit, which makes feature code easier to navigate.
- Features can be small or large without abandoning the same architecture.
- Contract and derivation boundaries are easier to test directly.

### Negative

- Features often span multiple files, which adds ceremony compared with ad hoc component state.
- Developers must learn listener middleware semantics and the intended file boundaries.
- State placement still requires engineering judgment; the decision cannot be
  reduced to a rigid component-depth or UI-element rule.

## Source Of Truth

The active implementation lives in frontend code, especially:

- `frontend/src/root-store/store.ts`
- `frontend/src/features/*/slice.ts`
- `frontend/src/features/*/listeners.ts`
- `frontend/src/features/*/selectors.ts`
- `frontend/src/features/*/store/slice.ts`
- `frontend/src/features/*/store/listeners.ts`
- `frontend/src/features/*/store/selectors.ts`

Representative examples:

- `frontend/src/features/agent-executions/store/` for keyed Redux-owned requests
- `frontend/src/features/evaluation-runs/store/` for keyed list and detail state
- `frontend/src/features/junjo-data/workflow-detail/store/` for synchronous shared selection state

## Related

- `TESTING.md`
- `frontend/src/__tests__/contracts/`
- `frontend/src/__tests__/integration/`
