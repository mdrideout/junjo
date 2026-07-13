import { JGraph, JGraphSchema } from '../../../junjo-graph/schemas'

import {
  JunjoExceptionEvent,
  JunjoExceptionEventSchema,
  JunjoHookErrorEvent,
  JunjoHookErrorEventSchema,
  JunjoSpanType,
  OtelSpan,
} from '../schemas/schemas'

const JUNJO_KEYS = {
  SPAN_TYPE: 'junjo.span_type',
  EXECUTABLE_DEFINITION_ID: 'junjo.executable_definition_id',
  EXECUTABLE_RUNTIME_ID: 'junjo.executable_runtime_id',
  EXECUTABLE_STRUCTURAL_ID: 'junjo.executable_structural_id',
  PARENT_EXECUTABLE_DEFINITION_ID: 'junjo.parent_executable_definition_id',
  PARENT_EXECUTABLE_RUNTIME_ID: 'junjo.parent_executable_runtime_id',
  PARENT_EXECUTABLE_STRUCTURAL_ID: 'junjo.parent_executable_structural_id',
  ENCLOSING_GRAPH_STRUCTURAL_ID: 'junjo.enclosing_graph_structural_id',
  WORKFLOW_EXECUTION_GRAPH_SNAPSHOT: 'junjo.workflow.execution_graph_snapshot',
  WORKFLOW_STATE_START: 'junjo.workflow.state.start',
  WORKFLOW_STATE_END: 'junjo.workflow.state.end',
  WORKFLOW_STORE_ID: 'junjo.workflow.store.id',
  WORKFLOW_PARENT_STORE_ID: 'junjo.workflow.parent_store.id',
  ERROR_TYPE: 'error.type',
  CANCELLED: 'junjo.cancelled',
  CANCELLED_REASON: 'junjo.cancelled_reason',
} as const

export class SpanAccessor {
  constructor(private span: OtelSpan) {}

  get raw(): OtelSpan {
    return this.span
  }

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

  get spanType(): JunjoSpanType {
    const value = this.attr<string>(JUNJO_KEYS.SPAN_TYPE)
    if (!value) {
      return JunjoSpanType.OTHER
    }

    if (Object.values(JunjoSpanType).includes(value as JunjoSpanType)) {
      return value as JunjoSpanType
    }

    return JunjoSpanType.OTHER
  }

  get junjoSpanType(): JunjoSpanType {
    return this.spanType
  }

  get executableDefinitionId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.EXECUTABLE_DEFINITION_ID)
  }

  get executableRuntimeId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.EXECUTABLE_RUNTIME_ID)
  }

  get executableStructuralId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.EXECUTABLE_STRUCTURAL_ID)
  }

  get parentExecutableDefinitionId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.PARENT_EXECUTABLE_DEFINITION_ID)
  }

  get parentExecutableRuntimeId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.PARENT_EXECUTABLE_RUNTIME_ID)
  }

  get parentExecutableStructuralId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.PARENT_EXECUTABLE_STRUCTURAL_ID)
  }

  get enclosingGraphStructuralId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.ENCLOSING_GRAPH_STRUCTURAL_ID)
  }

  get workflowExecutionGraphSnapshot(): JGraph | null {
    const raw = this.parseJsonAttr<object | null>(JUNJO_KEYS.WORKFLOW_EXECUTION_GRAPH_SNAPSHOT, null)
    if (!raw) {
      return null
    }

    const parsed = JGraphSchema.safeParse(raw)
    return parsed.success ? parsed.data : null
  }

  get workflowStateStart(): Record<string, unknown> {
    return this.parseJsonAttr<Record<string, unknown>>(JUNJO_KEYS.WORKFLOW_STATE_START, {})
  }

  get workflowStateEnd(): Record<string, unknown> {
    return this.parseJsonAttr<Record<string, unknown>>(JUNJO_KEYS.WORKFLOW_STATE_END, {})
  }

  get workflowStoreId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.WORKFLOW_STORE_ID)
  }

  get workflowParentStoreId(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.WORKFLOW_PARENT_STORE_ID)
  }

  get errorType(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.ERROR_TYPE)
  }

  get isCancelled(): boolean {
    return this.attr<boolean>(JUNJO_KEYS.CANCELLED) === true
  }

  get cancelledReason(): string | undefined {
    return this.attr<string>(JUNJO_KEYS.CANCELLED_REASON)
  }

  get exceptionEvents(): JunjoExceptionEvent[] {
    return this.span.events_json
      .map((event) => JunjoExceptionEventSchema.safeParse(event))
      .filter((result) => result.success)
      .map((result) => result.data)
  }

  get hookErrorEvents(): JunjoHookErrorEvent[] {
    return this.span.events_json
      .map((event) => JunjoHookErrorEventSchema.safeParse(event))
      .filter((result) => result.success)
      .map((result) => result.data)
  }

  get hasFailureSignal(): boolean {
    return Boolean(this.errorType) || this.exceptionEvents.length > 0 || this.hookErrorEvents.length > 0
  }

  get isWorkflow(): boolean {
    return this.spanType === JunjoSpanType.WORKFLOW
  }

  get isSubflow(): boolean {
    return this.spanType === JunjoSpanType.SUBFLOW
  }

  get isNode(): boolean {
    return this.spanType === JunjoSpanType.NODE
  }

  get isRunConcurrent(): boolean {
    return this.spanType === JunjoSpanType.RUN_CONCURRENT
  }

  get isJunjoSpan(): boolean {
    return this.spanType !== JunjoSpanType.OTHER
  }

  attr<T = unknown>(key: string): T | undefined {
    return this.span.attributes_json?.[key] as T | undefined
  }

  private parseJsonAttr<T>(key: string, defaultValue: T): T {
    const value = this.attr(key)
    if (value === null || value === undefined) {
      return defaultValue
    }

    if (typeof value === 'object') {
      return value as T
    }

    if (typeof value === 'string') {
      try {
        return JSON.parse(value) as T
      } catch {
        return defaultValue
      }
    }

    return defaultValue
  }
}

export function wrapSpan(span: OtelSpan): SpanAccessor {
  return new SpanAccessor(span)
}

export function wrapSpans(spans: OtelSpan[]): SpanAccessor[] {
  return spans.map((span) => new SpanAccessor(span))
}
