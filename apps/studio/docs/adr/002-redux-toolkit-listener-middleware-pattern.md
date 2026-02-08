# ADR-002: Redux Toolkit Listener Middleware Pattern

**Status:** Accepted
**Date:** 2026-01-08
**Author:** Matt

## Context

We need a consistent pattern for managing async operations (API calls, side effects) and derived state in our Redux store. The pattern should:

1. Separate concerns between state management, side effects, and derived data
2. Provide type safety throughout the data flow
3. Support memoized selectors for complex derived state
4. Be testable and maintainable
5. Avoid the complexity of redux-saga while being more powerful than simple thunks

## Decision

We use **Redux Toolkit's Listener Middleware** with a feature-based file structure. Each feature contains:

```
features/
  └── feature-name/
      ├── store/
      │   ├── slice.ts       # Redux slice with state and reducers
      │   ├── listeners.ts   # Listener middleware for async effects
      │   └── selectors.ts   # Memoized selectors for derived state
      ├── schemas/
      │   └── schemas.ts     # Zod schemas for domain types
      ├── fetch/
      │   └── operation.ts   # Plain fetch functions for API calls
      ├── utils/
      │   └── helpers.ts     # Accessor classes and utility functions
      └── FeaturePage.tsx    # React components
```

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         COMPONENT                                        │
│                                                                          │
│   const dispatch = useAppDispatch()                                      │
│   const derivedData = useAppSelector(selectDerivedData)                  │
│   dispatch(FeatureActions.triggerAction(payload))                        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
           │                                         ▲
           │ dispatch                                │ select
           ▼                                         │
┌─────────────────────────────────────────────────────────────────────────┐
│                         REDUX STORE                                      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    LISTENER MIDDLEWARE                           │    │
│  │                                                                  │    │
│  │  startListener({                                                 │    │
│  │    actionCreator: FeatureActions.triggerAction,                 │    │
│  │    effect: async (action, { dispatch, getState }) => {          │    │
│  │      dispatch(FeatureActions.setLoading(true))                  │    │
│  │      const data = await fetchData(action.payload)               │    │
│  │      dispatch(FeatureActions.setData(data))                     │    │
│  │      dispatch(FeatureActions.setLoading(false))                 │    │
│  │    }                                                             │    │
│  │  })                                                              │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                   │                                      │
│                                   ▼                                      │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                         REDUCER                                    │ │
│  │                                                                    │ │
│  │  setLoading: (state, action) => { state.loading = action.payload }│ │
│  │  setData: (state, action) => { state.data = action.payload }      │ │
│  │  setError: (state, action) => { state.error = action.payload }    │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   │                                      │
│                                   ▼                                      │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        SELECTORS                                   │ │
│  │                                                                    │ │
│  │  selectData = (state) => state.feature.data                       │ │
│  │  selectDerivedData = createSelector(                              │ │
│  │    [selectData, selectOtherData],                                 │ │
│  │    (data, other) => computeExpensiveDerivation(data, other)       │ │
│  │  )                                                                 │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. Slice (store/slice.ts)

The slice defines state shape and reducers. "Trigger" actions are empty reducers that exist only to be intercepted by listeners.

```typescript
import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../schemas/schemas'

interface TracesState {
  // Nested state for related data groups
  serviceNames: {
    data: string[]
    loading: boolean
    error: boolean
  }
  // Indexed data structure for efficient lookups
  traceSpans: {
    [traceId: string]: OtelSpan[]
  }
  loading: boolean
  error: boolean
}

const initialState: TracesState = {
  serviceNames: {
    data: [],
    loading: false,
    error: false,
  },
  traceSpans: {},
  loading: false,
  error: false,
}

export const tracesSlice = createSlice({
  name: 'tracesState',
  initialState,
  reducers: {
    // ========================================
    // Trigger Actions - Intercepted by listeners, no state change
    // ========================================
    fetchSpansByTraceId: (_state, _action: PayloadAction<{ traceId: string | undefined }>) => {
      // Handled by listener middleware
    },
    fetchServiceNames: (_state) => {
      // Handled by listener middleware
    },

    // ========================================
    // Mutation Actions - Called by listeners to update state
    // ========================================

    // Service Names
    setServiceNamesData: (state, action: PayloadAction<string[]>) => {
      state.serviceNames.data = action.payload
    },
    setServiceNamesLoading: (state, action: PayloadAction<boolean>) => {
      state.serviceNames.loading = action.payload
    },
    setServiceNamesError: (state, action: PayloadAction<boolean>) => {
      state.serviceNames.error = action.payload
    },

    // Traces Data
    setTracesData: (state, action: PayloadAction<{ traceId: string; data: OtelSpan[] }>) => {
      state.traceSpans[action.payload.traceId] = action.payload.data
    },
    setTracesLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setTracesError: (state, action: PayloadAction<boolean>) => {
      state.error = action.payload
    },
  },
})

export const TracesStateActions = tracesSlice.actions
export default tracesSlice.reducer
```

### 2. Listeners (store/listeners.ts)

Listeners intercept trigger actions and orchestrate async operations.

```typescript
import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { TracesStateActions } from './slice'
import { getTraceSpans } from '../fetch/get-trace-spans'
import { fetchServiceNames } from '../fetch/get-service-names'

export const tracesStateListenerMiddleware = createListenerMiddleware()

// Type the startListening function for proper RootState and AppDispatch inference
const startListener = tracesStateListenerMiddleware.startListening.withTypes<
  RootState,
  AppDispatch
>()

// Fetch Service Names
startListener({
  actionCreator: TracesStateActions.fetchServiceNames,
  effect: async (_action, listenerApi) => {
    // Clear errors and set loading
    listenerApi.dispatch(TracesStateActions.setServiceNamesError(false))
    listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(true))

    try {
      const data = await fetchServiceNames()
      listenerApi.dispatch(TracesStateActions.setServiceNamesData(data))
    } catch (error) {
      listenerApi.dispatch(TracesStateActions.setServiceNamesError(true))
    } finally {
      listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(false))
    }
  },
})

// Fetch Spans by Trace ID
startListener({
  actionCreator: TracesStateActions.fetchSpansByTraceId,
  effect: async (action, { getState, dispatch }) => {
    const { traceId } = action.payload
    if (!traceId) throw new Error('No traceId provided')

    // Prevent duplicate requests
    const loading = getState().tracesState.loading
    if (loading) return

    dispatch(TracesStateActions.setTracesError(false))
    dispatch(TracesStateActions.setTracesLoading(true))

    try {
      const data = await getTraceSpans(traceId)
      dispatch(TracesStateActions.setTracesData({ traceId, data }))
    } catch (error) {
      dispatch(TracesStateActions.setTracesError(true))
    } finally {
      dispatch(TracesStateActions.setTracesLoading(false))
    }
  },
})
```

### 3. Selectors (store/selectors.ts)

Memoized selectors for accessing and deriving state. Use `createSelector` for computed values.

```typescript
import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { OtelSpan } from '../schemas/schemas'

// ============================================================
// Basic Selectors - Direct state access
// ============================================================

export const selectTracesState = (state: RootState) => state.tracesState
export const selectTraceSpans = (state: RootState) => state.tracesState.traceSpans
export const selectTracesLoading = (state: RootState) => state.tracesState.loading
export const selectTracesError = (state: RootState) => state.tracesState.error

// Nested state selectors
export const selectServiceNamesLoading = (state: RootState) =>
  state.tracesState.serviceNames.loading
export const selectServiceNamesError = (state: RootState) =>
  state.tracesState.serviceNames.error
export const selectServiceNames = (state: RootState) =>
  state.tracesState.serviceNames.data

// ============================================================
// Parameterized Selectors - Accept props for dynamic selection
// ============================================================

/**
 * Select span by ID - parameterized selector with props
 */
export const selectSpanById = createSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined; spanId: string | undefined }) =>
      props.traceId,
    (_state: RootState, props: { traceId: string | undefined; spanId: string | undefined }) =>
      props.spanId,
  ],
  (traceSpans, traceId, spanId): OtelSpan | undefined => {
    if (!traceId || !spanId) return undefined
    const spans = traceSpans[traceId]
    if (!spans) return undefined
    return spans.find((item) => item.span_id === spanId)
  },
)

/**
 * Select all spans for a trace ID
 */
export const selectTraceSpansForTraceId = createSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined }) => props.traceId,
  ],
  (traceSpans, traceId): OtelSpan[] => {
    if (!traceId) return []
    return traceSpans[traceId] ?? []
  },
)

// ============================================================
// Composed Selectors - Build on other selectors
// ============================================================

/**
 * Select span and all its children (BFS traversal)
 */
export const selectSpanAndChildren = createSelector(
  [
    selectTraceSpansForTraceId,
    (_state: RootState, props: { spanId: string | undefined }) => props.spanId,
  ],
  (traceSpans, spanId): OtelSpan[] => {
    if (!traceSpans || !spanId) return []

    const startingSpan = traceSpans.find((item) => item.span_id === spanId)
    if (!startingSpan) return []

    // BFS to find all children
    const foundSpans: OtelSpan[] = [startingSpan]
    const queue: OtelSpan[] = [startingSpan]
    const visited = new Set<string>()
    visited.add(startingSpan.span_id)

    while (queue.length > 0) {
      const currentSpan = queue.shift()!
      const childSpans = traceSpans.filter((s) => s.parent_span_id === currentSpan.span_id)
      for (const child of childSpans) {
        if (!visited.has(child.span_id)) {
          foundSpans.push(child)
          queue.push(child)
          visited.add(child.span_id)
        }
      }
    }
    return foundSpans
  },
)

// ============================================================
// Custom Selector Creators - For specialized memoization
// ============================================================

/**
 * Custom equality check for workflow chains - only compare span IDs
 */
const workflowChainListEquality = (prevList: OtelSpan[], nextList: OtelSpan[]) => {
  if (!prevList || !nextList) return false
  if (prevList.length !== nextList.length) return false
  for (let i = 0; i < prevList.length; i++) {
    if (prevList[i].span_id !== nextList[i].span_id) return false
  }
  return true
}

/**
 * Custom selector creator with custom equality check
 */
const createWorkflowChainSelector = createSelectorCreator(
  lruMemoize,
  workflowChainListEquality
)

/**
 * Selector using custom equality for optimized re-renders
 */
export const identifySpanWorkflowChain = createWorkflowChainSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined }) => props.traceId,
    (_state: RootState, props: { workflowSpanId: string | undefined }) => props.workflowSpanId,
  ],
  (traceSpans, traceId, workflowSpanId): OtelSpan[] => {
    // ... complex derivation logic
    return []
  },
  {
    memoizeOptions: {
      resultEqualityCheck: workflowChainListEquality,
    },
  },
)
```

### 4. Schemas (schemas/schemas.ts)

Zod schemas for domain types and runtime validation.

```typescript
import { z } from 'zod'

// ============================================================
// Enums and Constants
// ============================================================

export enum JunjoSpanType {
  WORKFLOW = 'workflow',
  SUBFLOW = 'subflow',
  NODE = 'node',
  RUN_CONCURRENT = 'run_concurrent',
  OTHER = '',
}

// ============================================================
// Domain Schemas
// ============================================================

export const OtelSpanSchema = z.object({
  span_id: z.string(),
  trace_id: z.string(),
  service_name: z.string(),
  attributes_json: z.record(z.any()),
  start_time: z.string().datetime({ offset: true }),
  end_time: z.string().datetime({ offset: true }),
  events_json: z.array(z.record(z.any())),
  kind: z.string(),
  links_json: z.array(z.record(z.any())),
  name: z.string(),
  parent_span_id: z.string().nullable(),
  status_code: z.string(),
  status_message: z.string(),
  trace_flags: z.number(),
  trace_state: z.any(),
})
export type OtelSpan = z.infer<typeof OtelSpanSchema>

// ============================================================
// Event Schemas (for nested data)
// ============================================================

export const JunjoSetStateEventSchema = z.object({
  name: z.literal('set_state'),
  timeUnixNano: z.number(),
  attributes: z.object({
    id: z.string(),
    'junjo.state_json_patch': z.string(),
    'junjo.store.action': z.string(),
    'junjo.store.name': z.string(),
    'junjo.store.id': z.string(),
  }),
})
export type JunjoSetStateEvent = z.infer<typeof JunjoSetStateEventSchema>
```

### 5. Fetch Functions (fetch/*.ts)

Plain async functions for API calls with Zod validation.

```typescript
import { z } from 'zod'
import { OtelSpan, OtelSpanSchema } from '../schemas/schemas'
import { getApiHost } from '../../../config'

// Response schema for this endpoint
const GetTraceSpansResponseSchema = z.array(OtelSpanSchema)

export async function getTraceSpans(traceId: string): Promise<OtelSpan[]> {
  const endpoint = `/api/v1/observability/traces/${traceId}/spans`
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch spans')
  }

  const data = await response.json()

  // Validate response data against schema
  const validatedData = GetTraceSpansResponseSchema.parse(data)
  return validatedData
}
```

### 6. Utils / Accessor Classes (utils/span-accessor.ts)

Typed accessor classes for complex data structures with nested/dynamic attributes.

```typescript
import { JunjoSpanType, OtelSpan } from '../schemas/schemas'

// Attribute keys - single source of truth
const JUNJO_KEYS = {
  SPAN_TYPE: 'junjo.span_type',
  ID: 'junjo.id',
  WORKFLOW_STORE_ID: 'junjo.workflow.store_id',
} as const

/**
 * SpanAccessor - Typed accessor for OtelSpan with Junjo attribute extraction.
 */
export class SpanAccessor {
  constructor(private span: OtelSpan) {}

  // Core passthrough properties
  get spanId(): string { return this.span.span_id }
  get traceId(): string { return this.span.trace_id }
  get name(): string { return this.span.name }

  // Junjo-specific getters (extracted from attributes_json)
  get junjoSpanType(): JunjoSpanType {
    const value = this.attr<string>(JUNJO_KEYS.SPAN_TYPE)
    if (!value) return JunjoSpanType.OTHER
    if (Object.values(JunjoSpanType).includes(value as JunjoSpanType)) {
      return value as JunjoSpanType
    }
    return JunjoSpanType.OTHER
  }

  get workflowStoreId(): string {
    return this.attr<string>(JUNJO_KEYS.WORKFLOW_STORE_ID) ?? ''
  }

  // Convenience type checks
  get isWorkflow(): boolean { return this.junjoSpanType === JunjoSpanType.WORKFLOW }
  get isSubflow(): boolean { return this.junjoSpanType === JunjoSpanType.SUBFLOW }
  get isNode(): boolean { return this.junjoSpanType === JunjoSpanType.NODE }
  get isJunjoSpan(): boolean { return this.junjoSpanType !== JunjoSpanType.OTHER }

  // Generic attribute access
  attr<T = unknown>(key: string): T | undefined {
    return this.span.attributes_json?.[key] as T | undefined
  }

  get raw(): OtelSpan { return this.span }
}

// Factory functions
export function wrapSpan(span: OtelSpan): SpanAccessor {
  return new SpanAccessor(span)
}

export function wrapSpans(spans: OtelSpan[]): SpanAccessor[] {
  return spans.map((span) => new SpanAccessor(span))
}
```

### 7. Root Store (root-store/store.ts)

Configure the store with all reducers and listener middlewares.

```typescript
import { configureStore } from '@reduxjs/toolkit'
import tracesSlice from '../features/traces/store/slice'
import { tracesStateListenerMiddleware } from '../features/traces/store/listeners'
import { apiKeysReducer } from '../features/api-keys/slice'
import { apiKeysStateListenerMiddleware } from '../features/api-keys/listeners'

export const store = configureStore({
  reducer: {
    tracesState: tracesSlice,
    apiKeysState: apiKeysReducer,
    // ... other reducers
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      // IMPORTANT: Listener middleware must be prepended
      .prepend(
        tracesStateListenerMiddleware.middleware,
        apiKeysStateListenerMiddleware.middleware,
        // ... other listener middlewares
      ),
})

// Infer types from the store
export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
```

### 8. Typed Hooks (root-store/hooks.ts)

Export typed versions of useDispatch and useSelector.

```typescript
import { useDispatch, useSelector } from 'react-redux'
import type { RootState, AppDispatch } from './store'

// Use these throughout the app instead of plain useDispatch/useSelector
export const useAppDispatch = useDispatch.withTypes<AppDispatch>()
export const useAppSelector = useSelector.withTypes<RootState>()
```

### 9. Component Usage

```typescript
import { useEffect, useMemo } from 'react'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { TracesStateActions } from './store/slice'
import { selectTraceSpansForTraceId, selectTracesLoading } from './store/selectors'

function TraceDetails({ traceId }: { traceId: string }) {
  const dispatch = useAppDispatch()

  // Use selectors with props
  const selectorProps = useMemo(() => ({ traceId }), [traceId])
  const spans = useAppSelector((state) => selectTraceSpansForTraceId(state, selectorProps))
  const loading = useAppSelector(selectTracesLoading)

  // Dispatch trigger action
  useEffect(() => {
    dispatch(TracesStateActions.fetchSpansByTraceId({ traceId }))
  }, [dispatch, traceId])

  if (loading) return <div>Loading...</div>

  return (
    <div>
      {spans.map((span) => (
        <SpanRow key={span.span_id} span={span} />
      ))}
    </div>
  )
}
```

## Key Patterns

### Action Types

| Type | Purpose | Example | Reducer Body |
|------|---------|---------|--------------|
| **Trigger** | Intercepted by listener to start async work | `fetchData`, `deleteItem` | Empty (no-op) |
| **Mutation** | Actually modifies state | `setLoading`, `setData`, `setError` | Mutates state |

### Selector Types

| Type | Purpose | Example |
|------|---------|---------|
| **Basic** | Direct state access | `selectLoading = (state) => state.feature.loading` |
| **Parameterized** | Accept props for dynamic selection | `selectById(state, { id })` |
| **Composed** | Build on other selectors | `selectDerived = createSelector([selectA, selectB], (a, b) => ...)` |
| **Custom** | Specialized memoization | `createSelectorCreator(lruMemoize, customEquality)` |

### State Shape Convention

```typescript
interface FeatureState {
  // Main data (can be array, object, or indexed)
  data: DataType | DataType[] | { [key: string]: DataType }

  // Loading state
  loading: boolean

  // Error state
  error: boolean | string | null

  // Optional: for stale-while-revalidate
  lastUpdated: number | null

  // Nested data groups (if needed)
  relatedData: {
    data: RelatedType[]
    loading: boolean
    error: boolean
  }
}
```

### Listener Effect Pattern

```typescript
startListener({
  actionCreator: FeatureActions.triggerAction,
  effect: async (action, { dispatch, getState }) => {
    // 1. Early exit if already loading (prevent duplicate requests)
    if (getState().feature.loading) return

    // 2. Set loading state
    dispatch(FeatureActions.setLoading(true))
    dispatch(FeatureActions.setError(null))

    try {
      // 3. Perform async operation
      const data = await fetchData(action.payload)

      // 4. Update state with result
      dispatch(FeatureActions.setData(data))
    } catch (e) {
      // 5. Handle errors
      const message = e instanceof Error ? e.message : 'Unknown error'
      dispatch(FeatureActions.setError(message))
    } finally {
      // 6. Always clear loading
      dispatch(FeatureActions.setLoading(false))
    }
  },
})
```

## File Structure Summary

```
features/
  └── feature-name/
      ├── store/
      │   ├── slice.ts         # State + reducers (trigger + mutation)
      │   ├── listeners.ts     # Async effect handlers
      │   └── selectors.ts     # Memoized selectors
      ├── schemas/
      │   └── schemas.ts       # Zod schemas for domain types
      ├── fetch/
      │   ├── get-data.ts      # GET operations
      │   └── update-data.ts   # POST/PUT/DELETE operations
      ├── utils/
      │   └── accessor.ts      # Typed accessor classes
      └── *.tsx                # React components
```

## Consequences

### Benefits

1. **Clear separation**: State in slice, effects in listeners, derivation in selectors
2. **Type safety**: Full TypeScript support with inferred types
3. **Testability**: Each layer can be tested independently
4. **Performance**: Memoized selectors prevent unnecessary re-renders
5. **Predictable flow**: Actions always flow through the same path
6. **Composable**: Selectors can build on each other, listeners can dispatch triggers

### Trade-offs

1. **Boilerplate**: More files per feature than simple approaches
2. **Learning curve**: Developers must understand the pattern
3. **Indirection**: Trigger actions don't directly modify state

## Checklist for New Features

- [ ] Create `store/slice.ts` with state interface, initial state, trigger actions, mutation actions
- [ ] Create `store/listeners.ts` with typed startListening and effect handlers
- [ ] Create `store/selectors.ts` with basic and memoized selectors
- [ ] Create `schemas/schemas.ts` with Zod schemas for domain types
- [ ] Create `fetch/*.ts` with plain fetch functions and response validation
- [ ] Create `utils/*.ts` if accessor classes are needed for complex data
- [ ] Register reducer in `root-store/store.ts`
- [ ] Prepend listener middleware in `root-store/store.ts`
- [ ] Use `useAppDispatch` and `useAppSelector` in components

## References

- [Redux Toolkit Listener Middleware](https://redux-toolkit.js.org/api/createListenerMiddleware)
- [Reselect (createSelector)](https://redux-toolkit.js.org/api/createSelector)
- [Zod](https://zod.dev/) - TypeScript-first schema validation
