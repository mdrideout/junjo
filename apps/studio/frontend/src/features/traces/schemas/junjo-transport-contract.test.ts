import { describe, expect, it } from 'vitest'
import { loadAllJunjoTransportFixtures } from '../../../test-utils/junjo-fixture-loader'
import { OtelSpanSchema } from './schemas'

describe('Junjo transport contract', () => {
  const fixtures = loadAllJunjoTransportFixtures()

  it.each(fixtures)('parses current backend payload for %s', (fixture: (typeof fixtures)[number]) => {
    const parsedSpans = OtelSpanSchema.array().parse(fixture.spans)

    expect(parsedSpans).toHaveLength(fixture.spans.length)

    for (const span of parsedSpans) {
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
})
