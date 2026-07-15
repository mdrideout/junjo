import type { OtelSpan } from '../schemas/schemas'
import type { TraceEvidence } from '../schemas/trace-evidence'

export function makeTraceEvidence(spans: OtelSpan[]): TraceEvidence {
  return {
    trace_id: spans[0]?.trace_id ?? '00000000000000000000000000000000',
    spans,
    executables_by_span_id: {},
    operations_by_owner_runtime_id: {},
    stores_by_id: {},
    relationships_by_owner_span_id: {},
    diagnostics: [],
  }
}
