import { describe, expect, it } from 'vitest'
import {
  activeJunjoTransportContractVersion,
  loadAllJunjoTransportFixtures,
} from '../../../test-utils/junjo-fixture-loader'
import { OtelNanosecondsSchema, OtelSpanSchema } from './schemas'

describe('Junjo transport contract', () => {
  const fixtures = loadAllJunjoTransportFixtures()

  it.each(fixtures)('parses current backend payload for %s', (fixture: (typeof fixtures)[number]) => {
    const parsedSpans = OtelSpanSchema.array().parse(fixture.spans)

    expect(fixture.contract_version).toBe(activeJunjoTransportContractVersion)
    expect(parsedSpans).toHaveLength(fixture.spans.length)

    for (const span of parsedSpans) {
      expect(span.attributes_json['junjo.telemetry.contract_version']).toBe(
        activeJunjoTransportContractVersion,
      )
      const graphSnapshot = span.attributes_json['junjo.workflow.execution_graph_snapshot']
      if (graphSnapshot !== undefined) {
        expect(typeof graphSnapshot).toBe('string')
        expect(() => JSON.parse(graphSnapshot as string)).not.toThrow()
      }

      for (const event of span.events_json) {
        expect(event).toHaveProperty('name')
        expect(event).toHaveProperty('timeUnixNano')
        expect(event).not.toHaveProperty('time_unix_nano')
      }
    }
  })

  it('preserves the complete OTLP uint64 nanosecond domain as decimal text', () => {
    expect(OtelNanosecondsSchema.parse('18446744073709551615')).toBe(
      '18446744073709551615',
    )
    expect(OtelNanosecondsSchema.safeParse('18446744073709551616').success).toBe(false)
    expect(OtelNanosecondsSchema.safeParse(1783944000000000000).success).toBe(false)
    expect(OtelNanosecondsSchema.safeParse('01').success).toBe(false)
  })
})
