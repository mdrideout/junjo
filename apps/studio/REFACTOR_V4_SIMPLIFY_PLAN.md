# V4 Simplification: Move Junjo Attribute Extraction to Frontend

## Problem Statement

The current architecture extracts Junjo-specific attributes (e.g., `junjo.workflow.graph_structure`) from the generic `attributes_json` in the Python backend, then passes them as top-level fields in the API response. This creates several issues:

1. **Attribute key names defined in multiple places** - Backend Python files and frontend TypeScript must stay in sync
2. **Sync bugs** - The V4 refactor introduced a bug where the backend used `junjo.wf_graph_structure` but the Junjo library sends `junjo.workflow.graph_structure`
3. **Unnecessary complexity** - The backend does extraction work that provides no query/filtering benefit
4. **Maintenance burden** - Adding new Junjo attributes requires changes to backend extraction code

## Current Flow (Before)

```
OTLP Span (with attributes)
    ↓
Go Ingestion (stores raw protobuf in SQLite WAL)
    ↓
Python Backend (extracts junjo.* fields from attributes_json)  ← COMPLEXITY HERE
    ↓
API Response (junjo fields at top level + remaining attributes_json)
    ↓
Frontend (uses top-level junjo fields directly)
```

**Backend extraction code exists in:**
- `backend/app/features/span_ingestion/ingestion_client.py` - WAL data (lines 474-521)
- `backend/app/db_duckdb/datafusion_query.py` - Parquet data (lines 180-223)

## Proposed Flow (After)

```
OTLP Span (with attributes)
    ↓
Go Ingestion (stores raw protobuf in SQLite WAL)
    ↓
Python Backend (passes attributes_json through unchanged)  ← SIMPLIFIED
    ↓
API Response (all attributes in attributes_json)
    ↓
Frontend (SpanAccessor class extracts junjo fields)  ← LOGIC MOVES HERE
```

## Frontend Implementation

### New SpanAccessor Class

Create a utility class that wraps the raw API span and provides typed getters:

```typescript
// frontend/src/features/traces/utils/span-accessor.ts

import { JGraph, JGraphSchema } from '@/junjo-graph/schemas'

// Junjo attribute keys - single source of truth
const JUNJO_KEYS = {
  SPAN_TYPE: 'junjo.span_type',
  ID: 'junjo.id',
  PARENT_ID: 'junjo.parent_id',
  WORKFLOW_GRAPH_STRUCTURE: 'junjo.workflow.graph_structure',
  WORKFLOW_STATE_START: 'junjo.workflow.state.start',
  WORKFLOW_STATE_END: 'junjo.workflow.state.end',
  WORKFLOW_STORE_ID: 'junjo.workflow.store_id',
} as const

export class SpanAccessor {
  constructor(private span: OtelSpan) {}

  // Core span properties (passthrough)
  get spanId(): string { return this.span.span_id }
  get traceId(): string { return this.span.trace_id }
  get name(): string { return this.span.name }
  get serviceName(): string { return this.span.service_name }
  // ... other direct properties

  // Junjo-specific getters
  get junjoSpanType(): string {
    return this.attr(JUNJO_KEYS.SPAN_TYPE) ?? ''
  }

  get junjoId(): string {
    return this.attr(JUNJO_KEYS.ID) ?? ''
  }

  get junjoParentId(): string {
    return this.attr(JUNJO_KEYS.PARENT_ID) ?? ''
  }

  get workflowGraphStructure(): JGraph | null {
    const raw = this.attr(JUNJO_KEYS.WORKFLOW_GRAPH_STRUCTURE)
    if (!raw) return null
    const parsed = JGraphSchema.safeParse(raw)
    return parsed.success ? parsed.data : null
  }

  get workflowStateStart(): Record<string, unknown> {
    return this.attr(JUNJO_KEYS.WORKFLOW_STATE_START) ?? {}
  }

  get workflowStateEnd(): Record<string, unknown> {
    return this.attr(JUNJO_KEYS.WORKFLOW_STATE_END) ?? {}
  }

  get workflowStoreId(): string {
    return this.attr(JUNJO_KEYS.WORKFLOW_STORE_ID) ?? ''
  }

  // Helper to check span types
  get isWorkflow(): boolean {
    return this.junjoSpanType === 'workflow'
  }

  get isSubflow(): boolean {
    return this.junjoSpanType === 'subflow'
  }

  get isNode(): boolean {
    return this.junjoSpanType === 'node'
  }

  // Generic attribute access
  private attr<T = unknown>(key: string): T | undefined {
    return this.span.attributes_json?.[key] as T | undefined
  }
}

// Factory function for convenience
export function wrapSpan(span: OtelSpan): SpanAccessor {
  return new SpanAccessor(span)
}
```

### Usage in Components

```typescript
// Before (accessing extracted top-level fields)
const graphStructure = workflowSpan.junjo_wf_graph_structure
const isWorkflow = span.junjo_span_type === 'workflow'

// After (using SpanAccessor)
const accessor = wrapSpan(workflowSpan)
const graphStructure = accessor.workflowGraphStructure
const isWorkflow = accessor.isWorkflow
```

## Backend Simplification

### Remove from ingestion_client.py

```python
# REMOVE this extraction block (lines ~474-521):
def _convert_span_data_to_api_format(span_data):
    attributes = _parse_json_safe(span_data.attributes_json, {})

    # DELETE: junjo field extraction
    # junjo_id = attributes.pop("junjo.id", "")
    # junjo_parent_id = attributes.pop("junjo.parent_id", "")
    # ... etc

    return {
        "trace_id": span_data.trace_id,
        "span_id": span_data.span_id,
        # ... core fields ...
        "attributes_json": attributes,  # Pass through unchanged (no .pop())
        "events_json": events,
        # DELETE: top-level junjo fields
        # "junjo_id": junjo_id,
        # "junjo_wf_graph_structure": junjo_wf_graph_structure,
        # ... etc
    }
```

### Remove from datafusion_query.py

```python
# REMOVE the same extraction block (lines ~180-223):
def _convert_parquet_row_to_api_format(row):
    # DELETE: junjo field extraction
    # Just pass attributes through (no .pop())
    return {
        # ... core fields ...
        "attributes_json": attributes,  # Unchanged
        # DELETE: top-level junjo fields
    }
```

## Files to Update

### Backend (Simplify)

| File | Change |
|------|--------|
| `backend/app/features/span_ingestion/ingestion_client.py` | Remove junjo extraction from `_convert_span_data_to_api_format()` |
| `backend/app/db_duckdb/datafusion_query.py` | Remove junjo extraction from `_convert_parquet_row_to_api_format()` |

### Frontend (Add SpanAccessor)

| File | Change |
|------|--------|
| `frontend/src/features/traces/utils/span-accessor.ts` | **NEW** - SpanAccessor class |
| `frontend/src/features/traces/schemas/schemas.ts` | Remove `junjo_*` fields from `OtelSpanSchema` |
| `frontend/src/mermaidjs/RenderJunjoGraphList.tsx` | Use `SpanAccessor.workflowGraphStructure` |
| `frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx` | Use SpanAccessor |
| `frontend/src/features/traces/store/selectors.ts` | Use `SpanAccessor.isWorkflow`, `.isSubflow` |
| `frontend/src/features/traces/SpanRow.tsx` | Use `SpanAccessor.isWorkflow` |
| `frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx` | Use SpanAccessor |
| `frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx` | Use SpanAccessor |
| `frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx` | Use SpanAccessor |
| `frontend/src/features/junjo-data/span-lists/NestedWorkflowSpans.tsx` | Use SpanAccessor |

### Tests

| File | Change |
|------|--------|
| `backend/tests/test_v4_wal_fusion_integration.py` | Remove `junjo_*` fields from test assertions |
| `backend/tests/test_datafusion_query.py` | Update extraction tests |
| Frontend tests | Add SpanAccessor tests |

## What Stays Indexed (NO CHANGE)

The DuckDB `span_metadata` table still indexes `junjo_span_type` for query filtering:

```sql
-- v4_span_metadata.sql (NO CHANGE)
junjo_span_type VARCHAR(32),  -- Indexed for "get workflow spans" queries
openinference_span_kind VARCHAR(32),  -- Indexed for "get LLM spans" queries
```

This is extracted during **Parquet indexing** (not API response formatting), which is a separate concern and should remain. The parquet_reader extracts these for the metadata index.

## Related Schema Changes (Already Done)

These schema changes were completed in the V4 rearchitecture and are **not affected** by this refactoring:

| Change | Status |
|--------|--------|
| `services` table → `file_services` junction table | ✅ Done |
| Parquet filename: `{service}_{timestamp}_{uuid}.parquet` → `YYYYMMDD_HHMMSS_{hash}.parquet` | ✅ Done |
| WAL flush triggers immediate indexing | ✅ Done |

## Migration Path

1. **Create SpanAccessor** in frontend
2. **Update frontend components** to use SpanAccessor (can be done incrementally)
3. **Update frontend `OtelSpanSchema`** to remove `junjo_*` top-level fields
4. **Remove backend extraction** from both files
5. **Update backend tests**

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| Attribute key definitions | 2 places (Python + TS) | 1 place (TS only) |
| Backend complexity | Extraction + JSON parsing | Passthrough |
| Adding new Junjo attributes | Backend + Frontend changes | Frontend only |
| Risk of sync bugs | High | None |
| Type safety | Implicit | Explicit via SpanAccessor |
