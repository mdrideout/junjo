---
name: studio-frontend-react
description: Use when changing or reviewing Junjo AI Studio React components, Redux Toolkit state and listener patterns, frontend schemas, MSW/Vitest tests, or frontend feature organization.
---

# Studio Frontend React

## Use This Skill When

- The task touches `apps/studio/frontend/`.
- The task changes React component structure, state ownership, Redux Toolkit
  slices/listeners/selectors, frontend schemas, or frontend tests.
- The task changes frontend feature organization or a frontend-facing API
  contract.

## Boundaries

- This skill owns the workflow for Studio frontend work, not the architecture
  itself.
- `apps/studio/docs/adr/002-redux-toolkit-listener-middleware-pattern.md`
  owns state placement, listener middleware, and feature file roles.
- `apps/studio/docs/adr/004-events-json-contract.md` owns the `events_json`
  shape.
- Current code and tests own implementation details.

## Before Changing State

Determine:

1. Which component or feature semantically owns the value?
2. Which consumers read or change it, and how closely related are they in the
   component tree?
3. How long must the value live?
4. Is there already an authoritative local, URL, Context, or Redux value?
5. Do props still express a clear contract, or are unrelated components only
   forwarding them?
6. Does the transition require only synchronous state mutation, or does it
   have an asynchronous or external consequence?
7. Would broader ownership reduce more coordination than it adds?

Start with the narrowest correct owner. Do not move state into Redux merely
because a request is asynchronous or because props cross a fixed number of
components.

## Redux Guardrails

- Use typed hooks from `apps/studio/frontend/src/root-store/hooks.ts`.
- State-transition action types mutate slice state. Listener-trigger action
  types do not. A single action type must never do both.
- Reducers own synchronous invariants. Listeners own consequences of Redux
  trigger actions, including Redux-owned async work and cross-feature effects.
- Fetch modules own HTTP transport, and schemas parse responses at the runtime
  contract boundary.
- Do not introduce RTK Query or TanStack Query.
- Do not treat existing code that conflicts with the accepted ADR as a new
  architectural precedent.

## Workflow

1. Read `apps/studio/AGENTS.md`, the touched feature, and its tests.
2. Read ADR-002 before changing state ownership or async orchestration.
3. Read ADR-004 when parsing, rendering, or reshaping `events_json`.
4. When API contracts move, inspect
   `apps/studio/frontend/src/__tests__/contracts/` and
   `apps/studio/frontend/src/__tests__/integration/`.
5. Keep components and state logic explicit. Add abstractions only when
   established repetition has become brittle.

## Validation

Run the smallest relevant checks from `apps/studio/frontend`:

- `npm run test:run`
- `npm run lint`
- `npm run build` when UI or build behavior changes

If API contracts or event schemas change, run the owning contract or
integration tests as well.
