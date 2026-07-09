import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

type JunjoTransportFixture = {
  scenario: string
  trace_id: string
  service_name: string
  spans: unknown[]
}

const fixtureDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../test-fixtures/junjo-library-update',
)

export function loadJunjoTransportFixtureCase(caseName: string): JunjoTransportFixture {
  const fixturePath = path.join(fixtureDir, `${caseName}.json`)
  const fixtureText = fs.readFileSync(fixturePath, 'utf-8')
  return JSON.parse(fixtureText) as JunjoTransportFixture
}

export function loadAllJunjoTransportFixtures(): JunjoTransportFixture[] {
  return fs
    .readdirSync(fixtureDir)
    .filter((entry) => entry.endsWith('.json'))
    .sort()
    .map((entry) => loadJunjoTransportFixtureCase(entry.replace(/\.json$/, '')))
}
