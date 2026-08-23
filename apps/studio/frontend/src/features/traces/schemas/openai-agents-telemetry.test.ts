import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  OPENAI_AGENTS_KNOWN_SPAN_TYPES,
  parseOpenAIAgentsTelemetry,
} from './openai-agents-telemetry'

const contractDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../../../contracts/telemetry/integrations/openai_agents/v1',
)
const fixtureDirectory = path.join(contractDirectory, 'fixtures/valid')

function fixture(name: string): unknown {
  return JSON.parse(fs.readFileSync(path.join(fixtureDirectory, `${name}.json`), 'utf-8')) as unknown
}

describe('OpenAI Agents telemetry contract', () => {
  it.each([
    ['agent', 'agent'],
    ['response', 'response'],
  ])('parses the shared %s span fixture', (fixtureName, sourceType) => {
    const payload = fixture(fixtureName)
    const parsed = parseOpenAIAgentsTelemetry({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.span.type': sourceType,
      'junjo.openai_agents.span.data': JSON.stringify(payload),
    })

    expect(parsed).toMatchObject({
      kind: 'span',
      sourceType,
      knownSourceType: true,
      rawPayload: payload,
    })
  })

  it('parses the shared workflow trace fixture', () => {
    const payload = fixture('trace')
    const parsed = parseOpenAIAgentsTelemetry({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.trace.data': JSON.stringify(payload),
    })

    expect(parsed).toMatchObject({ kind: 'trace', rawPayload: payload })
  })

  it('retains an unknown source type through the generic representation', () => {
    const payload = {
      ...(fixture('agent') as Record<string, unknown>),
      source_type: 'future_operation',
      source_class: 'agents.future.FutureSpanData',
    }
    const parsed = parseOpenAIAgentsTelemetry({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.span.type': 'future_operation',
      'junjo.openai_agents.span.data': JSON.stringify(payload),
    })

    expect(parsed).toMatchObject({
      kind: 'span',
      sourceType: 'future_operation',
      knownSourceType: false,
      rawPayload: payload,
    })
  })

  it.each([
    ['malformed JSON', '{'],
    ['payload mismatch', JSON.stringify(fixture('response'))],
  ])('keeps marked but invalid %s inspectable', (_label, payload) => {
    const parsed = parseOpenAIAgentsTelemetry({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.span.type': 'agent',
      'junjo.openai_agents.span.data': payload,
    })

    expect(parsed?.kind).toBe('invalid')
  })

  it('ignores unmarked and future-version attributes', () => {
    expect(parseOpenAIAgentsTelemetry({})).toBeNull()
    expect(
      parseOpenAIAgentsTelemetry({
        'junjo.openai_agents.schema_version': 2,
        'junjo.openai_agents.span.type': 'agent',
        'junjo.openai_agents.span.data': JSON.stringify(fixture('agent')),
      }),
    ).toBeNull()
  })

  it('keeps the renderer coverage list aligned with the contract', () => {
    const attributeNames = JSON.parse(
      fs.readFileSync(path.join(contractDirectory, 'attribute-names.json'), 'utf-8'),
    ) as { known_span_types: string[] }

    expect(OPENAI_AGENTS_KNOWN_SPAN_TYPES).toEqual(attributeNames.known_span_types)
  })
})
