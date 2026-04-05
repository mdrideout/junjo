---
name: frontend-react
description: Use when changing or reviewing React components, Redux Toolkit state/listener patterns, frontend schemas, span event parsing, MSW/Vitest tests, or frontend feature organization. Owns frontend architecture and conventions, not backend or ingestion implementation details.
---

# Frontend React

## Use This Skill When

- The task touches `frontend/src/`.
- The task changes React component structure, Redux Toolkit slices/listeners/selectors, Zod schemas, span event parsing, MSW tests, or Vitest coverage.
- The task changes frontend feature organization or frontend-facing API contract handling.

## Do Not Use This Skill When

- The task is backend-only.
- The task is ingestion-only.
- The task is primarily a security/auth review without substantial frontend implementation work.

## Owned Paths

- `frontend/src/`
- `frontend/package.json`
- `frontend/vitest.config.ts`
- frontend contract and integration tests

## Workflow

1. Start from the touched feature code and existing store/test patterns.
2. Use ADRs only for current decisions:
   - `docs/adr/002-redux-toolkit-listener-middleware-pattern.md` for the default async orchestration split
   - `docs/adr/004-events-json-contract.md` when parsing, rendering, or reshaping `events_json`
3. Preserve the actual repo patterns in code. Do not import architecture from stale docs.
4. Assume Redux Toolkit listener middleware is the current repo pattern unless the code being changed clearly uses something else.
5. When contracts move, inspect the active contract and integration tests in `frontend/src/__tests__/contracts/` and `frontend/src/__tests__/integration/`.
6. Keep components and state logic explicit. Avoid introducing broad abstractions unless repetition is already brittle.
7. Use `TESTING.md` only for test strategy, not as a substitute for reading the current feature code.

## Validation Expectations

- Run the smallest relevant frontend verification:
  - `cd frontend && npm run test:run`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build` when UI/build behavior changes
- If API contracts or event schemas are affected, run the owning contract or integration tests rather than hand-waving schema compatibility.

## Source Of Truth Rules

- Frontend architecture lives in the current feature code and tests.
- `docs/adr/002-redux-toolkit-listener-middleware-pattern.md` owns the listener-middleware pattern, file-role boundaries, and allowed feature shapes. Concrete feature implementation still lives in code.
- `docs/adr/004-events-json-contract.md` owns the `events_json` event shape. Do not rename or reinterpret `timeUnixNano` in frontend-only code.
- Do not reintroduce stale claims such as TanStack Query usage if the code does not use it.
