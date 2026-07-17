#!/usr/bin/env node

import assert from 'node:assert/strict'
import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { parseArgs } from 'node:util'

import { chromium } from 'playwright'

import { describeActionableRequestFailure } from './request-failure-policy.mjs'

const EVIDENCE_FIELDS = new Set([
  'schema_version',
  'service_namespace',
  'service_name',
  'service_version',
  'trace_id',
  'agent_name',
  'agent_run_id',
  'agent_span_id',
  'tool_name',
  'tool_operation_sequence',
  'tool_span_id',
  'nested_workflow_name',
  'nested_workflow_span_id',
])

function requiredOrigin(value, name) {
  assert.ok(value, `${name} is required`)
  const parsed = new URL(value)
  assert.equal(parsed.pathname, '/', `${name} must be an HTTP origin without a path`)
  assert.equal(parsed.search, '', `${name} cannot include a query`)
  assert.equal(parsed.hash, '', `${name} cannot include a fragment`)
  assert.ok(['http:', 'https:'].includes(parsed.protocol), `${name} must use HTTP or HTTPS`)
  return parsed.origin
}

function requiredEnvironment(name) {
  const value = process.env[name]
  assert.ok(value, `${name} is required`)
  return value
}

function requiredText(value, name) {
  assert.equal(typeof value, 'string', `${name} must be text`)
  assert.ok(value.length > 0, `${name} cannot be empty`)
  return value
}

function readEvidence(value) {
  assert.ok(value !== null && typeof value === 'object' && !Array.isArray(value), 'evidence must be an object')
  assert.deepEqual(new Set(Object.keys(value)), EVIDENCE_FIELDS, 'evidence fields are incorrect')
  assert.equal(value.schema_version, 1, 'evidence schema version is incorrect')
  for (const name of EVIDENCE_FIELDS) {
    if (name !== 'schema_version' && name !== 'tool_operation_sequence') requiredText(value[name], name)
  }
  assert.equal(value.tool_operation_sequence, 2, 'Tool operation sequence is incorrect')
  assert.match(value.trace_id, /^[0-9a-f]{32}$/, 'trace_id is invalid')
  for (const name of EVIDENCE_FIELDS) {
    if (!name.endsWith('_span_id')) continue
    assert.match(value[name], /^[0-9a-f]{16}$/, `${name} is invalid`)
  }
  return value
}

async function visible(locator, description, timeout) {
  await locator.waitFor({ state: 'visible', timeout })
  assert.ok(await locator.count(), `${description} is absent`)
}

const { values } = parseArgs({
  options: {
    'frontend-url': { type: 'string' },
    'backend-url': { type: 'string' },
    evidence: { type: 'string' },
    screenshot: { type: 'string' },
    'timeout-milliseconds': { type: 'string', default: '30000' },
  },
  strict: true,
})

const frontendOrigin = requiredOrigin(values['frontend-url'], '--frontend-url')
const backendOrigin = requiredOrigin(values['backend-url'], '--backend-url')
assert.ok(values.evidence, '--evidence is required')
assert.ok(values.screenshot, '--screenshot is required')
const timeout = Number.parseInt(values['timeout-milliseconds'], 10)
assert.ok(Number.isSafeInteger(timeout) && timeout > 0, '--timeout-milliseconds must be a positive integer')
const evidence = readEvidence(JSON.parse(await readFile(values.evidence, 'utf8')))
const email = requiredEnvironment('JUNJO_STUDIO_E2E_EXISTING_EMAIL')
const password = requiredEnvironment('JUNJO_STUDIO_E2E_EXISTING_PASSWORD')
const screenshotPath = path.resolve(values.screenshot)

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
const browserFailures = []
const firstPartyOrigins = new Set([frontendOrigin, backendOrigin])
let observedTraceEvidence = false
let observedExecutionResolution = false
page.on('pageerror', (error) => browserFailures.push(`page error: ${error.message}`))
page.on('requestfailed', (request) => {
  const failure = describeActionableRequestFailure({
    requestUrl: request.url(),
    errorText: request.failure()?.errorText ?? 'unknown',
    firstPartyOrigins,
  })
  if (failure !== null) browserFailures.push(`${request.method()} ${failure}`)
})
page.on('response', (response) => {
  const url = new URL(response.url())
  if (url.pathname === '/api/v1/execution-resolution') {
    if (
      url.searchParams.get('service_namespace') === evidence.service_namespace
      && url.searchParams.get('service_name') === evidence.service_name
      && url.searchParams.get('executable_type') === 'agent'
      && url.searchParams.get('runtime_id') === evidence.agent_run_id
    ) {
      observedExecutionResolution = true
      if (url.origin !== backendOrigin || !response.ok()) {
        browserFailures.push(`Execution resolution response was ${response.status()} from ${url.origin}`)
      }
    }
  }
  const expectedPath = `/api/v1/trace-evidence/${evidence.trace_id}`
  if (url.pathname === expectedPath) {
    observedTraceEvidence = true
    if (url.origin !== backendOrigin || !response.ok()) {
      browserFailures.push(`TraceEvidence response was ${response.status()} from ${url.origin}`)
    }
  }
})

try {
  await page.goto(`${frontendOrigin}/sign-in`, { waitUntil: 'domcontentloaded', timeout })
  await page.getByPlaceholder('Email address').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForFunction(() => window.location.pathname !== '/sign-in', undefined, { timeout })

  const resolverUrl = new URL('/resolve/executable', frontendOrigin)
  resolverUrl.searchParams.set('service_namespace', evidence.service_namespace)
  resolverUrl.searchParams.set('service_name', evidence.service_name)
  resolverUrl.searchParams.set('executable_type', 'agent')
  resolverUrl.searchParams.set('runtime_id', evidence.agent_run_id)
  resolverUrl.searchParams.set('destination', 'detail')
  await page.goto(resolverUrl.href, { waitUntil: 'domcontentloaded', timeout })
  await visible(page.getByRole('heading', { level: 1, name: evidence.agent_name, exact: true }), 'Agent heading', timeout)
  assert.equal(page.url(), resolverUrl.href, 'semantic execution URL should remain canonical')
  await visible(page.getByRole('region', { name: 'Evidence integrity' }), 'evidence integrity', timeout)
  await visible(page.getByText('Contract evidence: complete', { exact: true }), 'complete evidence label', timeout)
  await visible(page.getByText(`run ${evidence.agent_run_id.slice(0, 6)}…${evidence.agent_run_id.slice(-6)}`, { exact: true }), 'Agent run identity', timeout)

  const operations = page.getByRole('region', { name: 'Realized Agent operations' })
  await visible(operations, 'realized operation timeline', timeout)
  const operationButtons = operations.getByRole('button')
  await operationButtons.nth(2).waitFor({ state: 'visible', timeout })
  assert.equal(await operationButtons.count(), 3, 'realized operation count is incorrect')
  for (const [index, expectedLabel] of ['1. Model', '2. Tool', '3. Model'].entries()) {
    await visible(
      operationButtons.nth(index).getByText(expectedLabel, { exact: true }),
      `operation ${index + 1} label ${expectedLabel}`,
      timeout,
    )
  }
  const toolButton = operationButtons.nth(1)
  await toolButton.click()
  await visible(operations.getByRole('heading', { level: 3, name: evidence.tool_name, exact: true }), 'Tool inspector', timeout)
  await visible(operations.getByText('Requested arguments', { exact: true }), 'Tool arguments', timeout)
  await visible(operations.getByText('Validated result', { exact: true }), 'Tool result', timeout)
  await visible(operations.getByText(evidence.nested_workflow_name, { exact: true }), 'nested Workflow', timeout)
  await visible(operations.getByText(`span ${evidence.nested_workflow_span_id}`, { exact: true }), 'nested Workflow span', timeout)

  await mkdir(path.dirname(screenshotPath), { recursive: true })
  await page.screenshot({ path: screenshotPath, fullPage: true })

  const nestedLink = operations.getByRole('link', { name: 'Open diagnostics', exact: true })
  await nestedLink.click()
  await page.waitForURL(
    `${frontendOrigin}/workflows/${encodeURIComponent(evidence.service_name)}/${evidence.trace_id}/${evidence.nested_workflow_span_id}`,
    { timeout },
  )
  await visible(
    page.getByText(`${evidence.nested_workflow_name} (${evidence.nested_workflow_span_id})`, { exact: true }),
    'nested Workflow identity',
    timeout,
  )
  await visible(page.getByRole('button', { name: 'Before', exact: true }), 'verified Workflow state', timeout)
  assert.equal(
    await page.getByRole('region', { name: 'Workflow Store diagnostics' }).count(),
    0,
    'healthy Workflow Store diagnostics should be silent',
  )

  assert.ok(observedTraceEvidence, 'the cohesive TraceEvidence request was not observed')
  assert.ok(observedExecutionResolution, 'the stable execution resolver request was not observed')
  assert.deepEqual(browserFailures, [], browserFailures.join('\n'))
} finally {
  await browser.close()
}

console.log(`Studio live Agent visual proof passed; screenshot: ${screenshotPath}`)
