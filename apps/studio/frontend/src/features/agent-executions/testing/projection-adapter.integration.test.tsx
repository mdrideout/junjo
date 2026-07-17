import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { AgentExecutionDetailView } from '../components/AgentExecutionDetailView'
import { parseBackendAgentProjectionFixtures } from './projection-adapter'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const studioRoot = path.resolve(testDirectory, '../../../../..')
const repositoryRoot = path.resolve(studioRoot, '../..')
const projectionPath = path.join(
  studioRoot,
  'backend/tests/generated/agent_semantic_projections.json',
)
const agentFixtureRoot = path.join(
  repositoryRoot,
  'contracts/telemetry/fixtures/agent',
)

function loadProjectionArtifact() {
  return parseBackendAgentProjectionFixtures(JSON.parse(fs.readFileSync(projectionPath, 'utf8')))
}

function loadValidFixtureCoverage(): { scenarioNames: string[]; ownerCount: number } {
  const fixtures = ['producer', 'consumer']
    .flatMap((fixtureSet) =>
      fs
        .readdirSync(path.join(agentFixtureRoot, fixtureSet))
        .filter((fileName) => fileName.endsWith('.json'))
        .map((fileName) =>
          JSON.parse(
            fs.readFileSync(path.join(agentFixtureRoot, fixtureSet, fileName), 'utf8'),
          ) as {
            scenario: string
            spans: Array<{ attributes_json: Record<string, unknown> }>
          },
        ),
    )
  return {
    scenarioNames: fixtures.map((fixture) => fixture.scenario).sort(),
    ownerCount: fixtures.reduce(
      (count, fixture) =>
        count + fixture.spans.filter((span) => span.attributes_json['junjo.span_type'] === 'agent').length,
      0,
    ),
  }
}

describe('API Contract: backend Agent semantic projections', () => {
  it('strictly parses every backend projection and covers every valid contract fixture', () => {
    const projections = loadProjectionArtifact()
    const { scenarioNames, ownerCount } = loadValidFixtureCoverage()
    const caseNames = projections.map((projection) => projection.case_name)

    expect(projections).toHaveLength(ownerCount)
    expect(new Set(caseNames).size).toBe(caseNames.length)
    for (const scenario of scenarioNames) {
      expect(
        caseNames.some((caseName) =>
          caseName === scenario || caseName.startsWith(`${scenario}__agent_`),
        ),
        `missing backend projection for ${scenario}`,
      ).toBe(true)
    }
    for (const projection of projections) {
      expect(projection.summary).toEqual(projection.detail.summary)
    }
  })

  it('renders every valid semantic detail without a raw-span or fake-Graph adapter', () => {
    const projections = loadProjectionArtifact()

    for (const projection of projections) {
      const view = render(
        <MemoryRouter>
          <AgentExecutionDetailView detail={projection.detail} />
        </MemoryRouter>,
      )
      expect(
        view.container.querySelector('h1')?.textContent,
        `detail heading missing for ${projection.case_name}`,
      ).toBe(projection.detail.summary.agent_name)
      expect(
        view.container.querySelector(
          'section[aria-label="Evidence integrity"]',
        ),
      ).not.toBeNull()
      view.unmount()
    }
  }, 60_000)
})
