import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

type JunjoTransportFixture = {
  contract_version: number
  scenario: string
  trace_id: string
  service_name: string
  spans: unknown[]
}

const contractDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../contracts/telemetry',
)
const fixtureDir = path.join(contractDir, 'fixtures/workflow')
const activeContractVersion = Number.parseInt(
  fs.readFileSync(path.join(contractDir, 'VERSION'), 'utf-8').trim(),
  10,
)

export function loadJunjoTransportFixtureCase(caseName: string): JunjoTransportFixture {
  const fixturePath = path.join(fixtureDir, `${caseName}.json`)
  const fixtureText = fs.readFileSync(fixturePath, 'utf-8')
  const fixture = JSON.parse(fixtureText) as JunjoTransportFixture
  if (fixture.contract_version !== activeContractVersion) {
    throw new Error(
      `Fixture ${caseName} targets telemetry contract ${fixture.contract_version}; expected ${activeContractVersion}`,
    )
  }
  return fixture
}

export function loadAllJunjoTransportFixtures(): JunjoTransportFixture[] {
  return fs
    .readdirSync(fixtureDir)
    .filter((entry) => entry.endsWith('.json'))
    .sort()
    .map((entry) => loadJunjoTransportFixtureCase(entry.replace(/\.json$/, '')))
}
