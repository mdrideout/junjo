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

  await page.goto(
    `${frontendOrigin}/evaluation-runs/${encodeURIComponent(evidence.candidate_run_id)}`,
    { waitUntil: 'domcontentloaded', timeout },
  )
  await visible(page.getByRole('heading', { level: 1, name: 'candidate', exact: true }), 'candidate Run heading', timeout)
  await visible(page.getByText(evidence.candidate_run_id, { exact: true }), 'candidate Run identity', timeout)
  await visible(page.getByText(evidence.dataset_id, { exact: true }), 'Dataset identity', timeout)
  await visible(page.getByText('completed', { exact: true }).first(), 'completed Run status', timeout)

  const detailRows = page.getByRole('table').getByRole('row').filter({ has: page.getByText('passed', { exact: true }) })
  assert.equal(await detailRows.count(), evidence.case_count, 'Run detail did not render every passed Case')
  assert.equal(
    await page.getByRole('link', { name: /^Open subject evidence for / }).count(),
    evidence.case_count,
    'Run detail did not expose subject evidence for every Case',
  )
  await mkdir(path.dirname(screenshotPath), { recursive: true })
  await page.screenshot({ path: screenshotPath, fullPage: true })

  const comparisonUrl = new URL('/evaluation-runs/compare', frontendOrigin)
  comparisonUrl.searchParams.set('baseline_run_id', evidence.baseline_run_id)
  comparisonUrl.searchParams.set('candidate_run_id', evidence.candidate_run_id)
  await page.goto(comparisonUrl.href, { waitUntil: 'domcontentloaded', timeout })
  await visible(page.getByRole('heading', { level: 1, name: 'Baseline and candidate', exact: true }), 'comparison heading', timeout)
  await visible(page.getByText(evidence.baseline_run_id, { exact: true }), 'baseline Run identity', timeout)
  await visible(page.getByText(evidence.candidate_run_id, { exact: true }), 'candidate comparison identity', timeout)
  const comparisonRows = page.getByRole('table').getByRole('row').filter({
    has: page.getByRole('link', { name: /^Open candidate evidence for / }),
  })
  assert.equal(await comparisonRows.count(), evidence.case_count, 'comparison did not render every Case')
  assert.deepEqual(browserFailures, [], browserFailures.join('\n'))
} finally {
  await browser.close()
}

console.log(`Studio live evaluation proof passed; screenshot: ${screenshotPath}`)
