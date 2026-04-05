# ADR-002: Redux Toolkit Listener Middleware Pattern

## Status

Accepted

## Context

The frontend needs one durable pattern for:

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

### Responsibility Split

The frontend uses these ownership rules:

- components own rendering, user interaction, and dispatching trigger actions
- slices own state shape and synchronous reducers
- listener middleware owns async orchestration and side effects
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
  store/
    slice.ts               # Required when the feature owns Redux state
    listeners.ts           # Required when the feature owns async orchestration
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
  slice.ts
  listeners.ts
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
- reducers do not perform fetches, parsing, or unrelated derivation logic

#### Listeners

- `listeners.ts` or `store/listeners.ts` owns async flows and side effects
- listeners call fetch modules, dispatch mutation actions, and read current state when needed
- listener middleware must be prepended in the root store so it can intercept trigger actions consistently

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

- components select state, render UI, and dispatch trigger actions
- components should not inline transport code, schema parsing, or complex reusable derivation

### Store Registration

At the app level:

- reducers are registered in `frontend/src/root-store/store.ts`
- each feature listener middleware is prepended in `frontend/src/root-store/store.ts`
- typed store hooks remain the default component entry point for dispatch and selection

## Invariants

These are part of the decision:

- Redux listener middleware is the default async orchestration mechanism
- side effects stay out of reducers
- request code stays out of components
- reusable derivation stays out of components when selectors are appropriate
- runtime contract parsing stays explicit at schema boundaries
- feature structure may vary, but file roles must remain clear

## Consequences

### Positive

- The repo has one default async state pattern.
- Side effects stay separate from reducers and UI.
- File roles stay explicit, which makes feature code easier to navigate.
- Features can be small or large without abandoning the same architecture.
- Contract and derivation boundaries are easier to test directly.

### Negative

- Features often span multiple files, which adds ceremony compared with ad hoc component state.
- Developers must learn listener middleware semantics and the intended file boundaries.
- Small one-off flows still need to respect the shared pattern instead of inventing local shortcuts.

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

- `frontend/src/features/traces/store/`
- `frontend/src/features/users/`
- `frontend/src/features/api-keys/`
- `frontend/src/features/settings/`

## Related

- `TESTING.md`
- `frontend/src/__tests__/contracts/`
- `frontend/src/__tests__/integration/`
