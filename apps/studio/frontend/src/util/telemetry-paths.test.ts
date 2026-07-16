import { describe, expect, it } from 'vitest'
import {
  logsPath,
  observabilityServicePath,
  tracesPath,
  workflowPath,
} from './telemetry-paths'

describe('telemetry path builders', () => {
  it.each(['slash/name', 'percent%name', 'query?name', 'hash#name', 'space name', '日本語']) (
    'encodes opaque service names exactly once: %s',
    (serviceName) => {
      const encoded = encodeURIComponent(serviceName)
      expect(logsPath(serviceName)).toBe(`/logs/${encoded}`)
      expect(tracesPath(serviceName, 'trace/id')).toBe(`/traces/${encoded}/trace%2Fid`)
      expect(workflowPath(serviceName, 'trace?', 'workflow#')).toBe(
        `/workflows/${encoded}/trace%3F/workflow%23`,
      )
      expect(observabilityServicePath(serviceName, 'workflows')).toBe(
        `/api/v1/observability/services/${encoded}/workflows`,
      )
    },
  )

  it('rejects missing mandatory segments instead of shifting later values', () => {
    expect(() => logsPath(undefined)).toThrow('missing segment')
    expect(() => tracesPath(undefined, 'trace')).toThrow('missing segment')
    expect(() => tracesPath('service', undefined, 'span')).toThrow('without a trace segment')
    expect(() => workflowPath('service', undefined, 'workflow')).toThrow('missing segment')
  })
})
