const segment = (value: string | undefined): string => {
  if (value === undefined) throw new Error('Cannot build a telemetry path with a missing segment.')
  return encodeURIComponent(value)
}

export function logsPath(serviceName: string | undefined): string {
  return `/logs/${segment(serviceName)}`
}

export function agentPath(traceId: string, agentSpanId: string): string {
  return `/agents/${segment(traceId)}/${segment(agentSpanId)}`
}

export function tracesPath(serviceName: string | undefined, traceId?: string, spanId?: string): string {
  if (spanId !== undefined && traceId === undefined) {
    throw new Error('Cannot build a span path without a trace segment.')
  }
  const suffix = [traceId, spanId]
    .filter((part): part is string => part !== undefined)
    .map(segment)
    .join('/')
  return `/traces/${segment(serviceName)}${suffix === '' ? '' : `/${suffix}`}`
}

export function workflowPath(
  serviceName: string | undefined,
  traceId: string | undefined,
  workflowSpanId: string | undefined,
  spanId?: string,
): string {
  const base = `/workflows/${segment(serviceName)}/${segment(traceId)}/${segment(workflowSpanId)}`
  return spanId === undefined ? base : `${base}/${segment(spanId)}`
}

export function promptPlaygroundPath(basePath: string): string {
  return `${basePath}/prompt-playground`
}

export function observabilityServicePath(serviceName: string | undefined, resource: string): string {
  return `/api/v1/observability/services/${segment(serviceName)}/${resource}`
}

export function observabilityTraceSpansPath(traceId: string | undefined, spanId?: string): string {
  const suffix = spanId === undefined ? '' : `/${segment(spanId)}`
  return `/api/v1/observability/traces/${segment(traceId)}/spans${suffix}`
}
