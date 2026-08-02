#!/usr/bin/env node

import assert from 'node:assert/strict'
import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { parseArgs } from 'node:util'

import { chromium } from 'playwright'

import { describeActionableRequestFailure } from './request-failure-policy.mjs'

const EVIDENCE_FIELDS = new Set([
  'schema_version',
  'application_key',
  'dataset_id',
  'baseline_run_id',
  'candidate_run_id',
  'case_count',
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

function readEvidence(value) {
  assert.ok(value !== null && typeof value === 'object' && !Array.isArray(value), 'evidence must be an object')
  assert.deepEqual(new Set(Object.keys(value)), EVIDENCE_FIELDS, 'evidence fields are incorrect')
  assert.equal(value.schema_version, 1, 'evidence schema version is incorrect')
  for (const field of ['application_key', 'dataset_id', 'baseline_run_id', 'candidate_run_id']) {
    assert.equal(typeof value[field], 'string', `${field} must be text`)
    assert.ok(value[field].length > 0, `${field} cannot be empty`)
  }
  assert.equal(value.case_count, 3, 'evaluation Case count is incorrect')
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
  if (firstPartyOrigins.has(url.origin) && url.pathname.startsWith('/api/') && !response.ok()) {
    browserFailures.push(`${response.request().method()} ${url.href} returned ${response.status()}`)
  }
})

try {
  await page.goto(`${frontendOrigin}/sign-in`, { waitUntil: 'domcontentloaded', timeout })
  await page.getByPlaceholder('Email address').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForFunction(() => window.location.pathname !== '/sign-in', undefined, { timeout })

  await page.goto(`${frontendOrigin}/evaluation-runs`, {
    waitUntil: 'domcontentloaded',
    timeout,
  })
  await visible(page.getByRole('heading', { level: 1, name: 'Evaluations', exact: true }), 'Evaluations heading', timeout)
  await page.getByRole('combobox', { name: 'Dataset' }).selectOption(evidence.dataset_id)
  await visible(page.getByRole('link', { name: 'candidate', exact: true }), 'candidate history row', timeout)
  await page.getByRole('link', { name: 'Evaluation E2E', exact: true }).click()
  await visible(page.getByRole('heading', { level: 1, name: 'Evaluation E2E', exact: true }), 'dataset detail heading', timeout)
  await visible(page.getByRole('heading', { level: 2, name: 'Tests', exact: true }), 'dataset Tests heading', timeout)
  await visible(page.getByRole('heading', { level: 2, name: 'Run history', exact: true }), 'dataset Run history heading', timeout)
  await page.goto(`${frontendOrigin}/evaluation-runs?dataset_id=${encodeURIComponent(evidence.dataset_id)}&limit=50`, {
    waitUntil: 'domcontentloaded',
    timeout,
  })
  await page.getByRole('combobox', { name: 'Target scope' }).selectOption({
    label: 'agent · double.agent · input v1',
  })
  await visible(page.getByText('0% pass', { exact: true }), 'scoped candidate pass rate', timeout)
  await page.getByRole('link', { name: 'candidate', exact: true }).click()

  await visible(page.getByRole('heading', { level: 1, name: 'candidate', exact: true }), 'candidate Run heading', timeout)
  await visible(page.getByText('Git Commit', { exact: true }), 'Git Commit label', timeout)
  await visible(page.getByRole('heading', { level: 2, name: 'Evaluation results', exact: true }), 'evaluation results heading', timeout)
  await visible(page.getByText('completed', { exact: true }).first(), 'completed Run status', timeout)

  assert.equal(await page.getByText('passed', { exact: true }).count(), 2, 'Run detail passed count changed')
  assert.equal(await page.getByText('failed', { exact: true }).count(), 1, 'Run detail failed count changed')
  const executionLinks = page.getByRole('link', {
    name: 'View spans',
  })
  assert.equal(
    await executionLinks.count(),
    evidence.case_count,
    'Run detail did not expose an execution for every Case',
  )
  const executionHrefs = await executionLinks.evaluateAll((links) =>
    links.map((link) => link.getAttribute('href')).filter((href) => href !== null))
  for (const href of executionHrefs) {
    const resolutionResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/execution-resolution'
        && response.ok(),
      { timeout },
    )
    await page.goto(new URL(href, frontendOrigin).href, {
      waitUntil: 'domcontentloaded',
      timeout,
    })
    await resolutionResponse
    assert.equal(
      await page.getByRole('alert').filter({
        hasText: 'Execution diagnostics could not be loaded.',
      }).count(),
      0,
      `execution link failed: ${href}`,
    )
  }
  await page.goto(
    `${frontendOrigin}/evaluation-runs/${encodeURIComponent(evidence.candidate_run_id)}`,
    { waitUntil: 'domcontentloaded', timeout },
  )
  await visible(page.getByRole('heading', { level: 1, name: 'candidate', exact: true }), 'candidate Run heading', timeout)
  await mkdir(path.dirname(screenshotPath), { recursive: true })
  await page.screenshot({ path: screenshotPath, fullPage: true })

  const comparisonUrl = new URL('/evaluation-runs/compare', frontendOrigin)
  comparisonUrl.searchParams.set('baseline_run_id', evidence.baseline_run_id)
  comparisonUrl.searchParams.set('candidate_run_id', evidence.candidate_run_id)
  comparisonUrl.searchParams.set('target_kind', 'agent')
  comparisonUrl.searchParams.set('target_key', 'double.agent')
  comparisonUrl.searchParams.set('input_version', '1')
  comparisonUrl.searchParams.set('evaluation_name', 'Exact double result')
  await page.goto(comparisonUrl.href, { waitUntil: 'domcontentloaded', timeout })
  await visible(page.getByRole('heading', { level: 1, name: 'Compare runs', exact: true }), 'comparison heading', timeout)
  await visible(page.getByRole('heading', { level: 2, name: 'baseline', exact: true }), 'baseline Run label', timeout)
  await visible(page.getByRole('heading', { level: 2, name: 'candidate', exact: true }), 'candidate Run label', timeout)
  const comparisonRows = page.getByRole('table').getByRole('row').filter({
    has: page.getByRole('link', { name: 'View candidate spans' }),
  })
  assert.equal(await comparisonRows.count(), 1, 'scoped comparison did not render the Agent Case')
  await visible(comparisonRows.getByText('double.agent', { exact: true }), 'comparison target scope', timeout)
  await visible(
    comparisonRows.getByText('Exact double result', { exact: true }),
    'comparison evaluation name',
    timeout,
  )
  await visible(comparisonRows.getByText('regressed', { exact: true }), 'regressed transition', timeout)
  assert.deepEqual(browserFailures, [], browserFailures.join('\n'))
} finally {
  await browser.close()
}

console.log(`Studio live evaluation proof passed; screenshot: ${screenshotPath}`)
