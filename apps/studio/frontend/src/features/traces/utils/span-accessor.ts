/**
 * SpanAccessor - Typed accessor for OtelSpan with Junjo attribute extraction.
 *
 * This class provides typed getters for Junjo-specific attributes that are
 * stored in the generic attributes_json field. It serves as the single source
 * of truth for Junjo attribute key names.
 *
 * Usage:
 *   const accessor = wrapSpan(span)
 *   if (accessor.isWorkflow) {
 *     const graph = accessor.workflowGraphStructure
 *   }
 */

import { JGraph, JGraphSchema } from '../../../junjo-graph/schemas'

import { JunjoSpanType, OtelSpan } from '../schemas/schemas'

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

  // ============================================================
  // Core span properties (passthrough)
  // ============================================================

  get spanId(): string {
    return this.span.span_id
  }
  get traceId(): string {
    return this.span.trace_id
  }
  get parentSpanId(): string | null {
    return this.span.parent_span_id
  }
  get name(): string {
    return this.span.name
  }
  get serviceName(): string {
    return this.span.service_name
  }
  get kind(): string {
    return this.span.kind
  }
  get startTime(): string {
    return this.span.start_time
  }
  get endTime(): string {
    return this.span.end_time
  }
  get statusCode(): string {
    return this.span.status_code
  }
  get statusMessage(): string {
    return this.span.status_message
  }
  get attributesJson(): Record<string, unknown> {
    return this.span.attributes_json
  }
  get eventsJson(): Record<string, unknown>[] {
    return this.span.events_json
  }
  get linksJson(): Record<string, unknown>[] {
    return this.span.links_json
  }

  // ============================================================
  // Junjo-specific getters (extracted from attributes_json)
  // ============================================================

  get junjoSpanType(): JunjoSpanType {
    const value = this.attr<string>(JUNJO_KEYS.SPAN_TYPE)
    if (!value) return JunjoSpanType.OTHER
    // Validate against enum values
    if (Object.values(JunjoSpanType).includes(value as JunjoSpanType)) {
      return value as JunjoSpanType
    }
    return JunjoSpanType.OTHER
  }

  get junjoId(): string {
    return this.attr<string>(JUNJO_KEYS.ID) ?? ''
  }

  get junjoParentId(): string {
    return this.attr<string>(JUNJO_KEYS.PARENT_ID) ?? ''
  }

  get workflowGraphStructure(): JGraph | null {
    const raw = this.parseJsonAttr<object | null>(JUNJO_KEYS.WORKFLOW_GRAPH_STRUCTURE, null)
    if (!raw) return null
    const parsed = JGraphSchema.safeParse(raw)
    return parsed.success ? parsed.data : null
  }

  get workflowStateStart(): Record<string, unknown> {
    return this.parseJsonAttr<Record<string, unknown>>(JUNJO_KEYS.WORKFLOW_STATE_START, {})
  }

  get workflowStateEnd(): Record<string, unknown> {
    return this.parseJsonAttr<Record<string, unknown>>(JUNJO_KEYS.WORKFLOW_STATE_END, {})
  }

  get workflowStoreId(): string {
    return this.attr<string>(JUNJO_KEYS.WORKFLOW_STORE_ID) ?? ''
  }

  // ============================================================
  // Convenience helpers for span type checks
  // ============================================================

  get isWorkflow(): boolean {
    return this.junjoSpanType === JunjoSpanType.WORKFLOW
  }

  get isSubflow(): boolean {
    return this.junjoSpanType === JunjoSpanType.SUBFLOW
  }

  get isNode(): boolean {
    return this.junjoSpanType === JunjoSpanType.NODE
  }

  get isRunConcurrent(): boolean {
    return this.junjoSpanType === JunjoSpanType.RUN_CONCURRENT
  }

  get isJunjoSpan(): boolean {
    return this.junjoSpanType !== JunjoSpanType.OTHER
  }

  // ============================================================
  // Generic attribute access
  // ============================================================

  /**
   * Get a raw attribute value by key.
   */
  attr<T = unknown>(key: string): T | undefined {
    return this.span.attributes_json?.[key] as T | undefined
  }

  /**
   * Parse a JSON string value, or return the value if already an object.
   * Returns the default if parsing fails or value is null/undefined.
   */
  private parseJsonAttr<T>(key: string, defaultValue: T): T {
    const value = this.attr(key)
    if (value === null || value === undefined) return defaultValue

    // Already an object, return as-is
    if (typeof value === 'object') return value as T

    // Try to parse JSON string
    if (typeof value === 'string') {
      try {
        return JSON.parse(value) as T
      } catch {
        return defaultValue
      }
    }

    return defaultValue
  }

  /**
   * Get the underlying raw span object.
   */
  get raw(): OtelSpan {
    return this.span
  }
}

/**
 * Factory function to wrap a span with SpanAccessor.
 */
export function wrapSpan(span: OtelSpan): SpanAccessor {
  return new SpanAccessor(span)
}

/**
 * Factory function to wrap multiple spans.
 */
export function wrapSpans(spans: OtelSpan[]): SpanAccessor[] {
  return spans.map((span) => new SpanAccessor(span))
}
