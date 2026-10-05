#!/usr/bin/env node

// Drives Studio's real pages in several browser tabs for a fixed time, the way
// a person moves between them, and records what every page showed and how
// every API request was answered. The benchmark harness runs it while its
// exporters send spans: see ingestion/benchmarks/README.md.
//
// It asserts nothing about what it records. A page that shows an error or no
// rows is a recorded outcome, and the reader compares runs.

import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { parseArgs } from 'node:util'

import { chromium } from 'playwright'

import { describeActionableRequestFailure } from './request-failure-policy.mjs'

// What each page shows when its request failed.
const SERVICES_ERROR = 'Error fetching app names.'
const TRACES_ERROR = 'Error loading traces.'
const WORKFLOWS_ERROR = 'Error loading workflow executions'
const TRACE_DETAIL_ERROR = 'Error loading spans.'
const TRACE_DETAIL_EMPTY = 'No spans found.'
const LOADING = 'Loading...'

function requiredOrigin(value, name) {
  assert.ok(value, `${name} is required`)
  const parsed = new URL(value)
  assert.equal(parsed.pathname, '/', `${name} must be an HTTP origin without a path`)
  assert.ok(['http:', 'https:'].includes(parsed.protocol), `${name} must use HTTP or HTTPS`)
  return parsed.origin
}

function requiredEnvironment(name) {
  const value = process.env[name]
  assert.ok(value, `${name} is required`)
  return value
}

function positiveInteger(value, name) {
  const parsed = Number.parseInt(value, 10)
  assert.ok(Number.isSafeInteger(parsed) && parsed > 0, `${name} must be a positive integer`)
  return parsed
}

const { values } = parseArgs({
  options: {
    'studio-url': { type: 'string' },
    services: { type: 'string' },
    tabs: { type: 'string', default: '4' },
    'duration-seconds': { type: 'string' },
    output: { type: 'string' },
    'timeout-milliseconds': { type: 'string', default: '60000' },
    // Also load the two pages whose queries read a service's whole history.
    'history-pages': { type: 'boolean', default: false },
    // Also list the traces of one API key, chosen in the Traces page's picker.
    'api-key-filter': { type: 'boolean', default: false },
  },
  strict: true,
})

const studioOrigin = requiredOrigin(values['studio-url'], '--studio-url')
assert.ok(values.services, '--services is required')
assert.ok(values.output, '--output is required')
const services = values.services.split(',')
const tabs = positiveInteger(values.tabs, '--tabs')
const durationMilliseconds = positiveInteger(values['duration-seconds'], '--duration-seconds') * 1000
// How long one page may take to show rows, an error, or nothing. A page that
// takes longer is recorded as a timeout and the tab moves on.
const timeout = positiveInteger(values['timeout-milliseconds'], '--timeout-milliseconds')
const email = requiredEnvironment('JUNJO_STUDIO_E2E_EXISTING_EMAIL')
const password = requiredEnvironment('JUNJO_STUDIO_E2E_EXISTING_PASSWORD')
const firstPartyOrigins = new Set([studioOrigin])

/** One API route with its identifiers and service names replaced. */
function routeOf(url) {
  const parsed = new URL(url)
  let route = parsed.pathname
    .replace(/\/services\/[^/]+\//, '/services/{service}/')
    .replace(/\/[0-9a-f]{32}(?=\/|$)/g, '/{trace}')
    .replace(/\/[0-9a-f]{16}(?=\/|$)/g, '/{span}')
  if (parsed.searchParams.get('has_llm') === 'true') route += '?has_llm=true'
  return route
}

const responses = []
const requestFailures = []
const pageErrors = []
const actions = []

function record(page) {
  const started = new Map()
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) started.set(request, Date.now())
  })
  page.on('response', (response) => {
    const request = response.request()
    const begin = started.get(request)
    if (begin === undefined) return
    started.delete(request)
    responses.push({ route: routeOf(request.url()), status: response.status(), ms: Date.now() - begin })
  })
  page.on('requestfailed', (request) => {
    started.delete(request)
    // Leaving a page cancels its requests. That is the browser, not Studio.
    const failure = describeActionableRequestFailure({
      requestUrl: request.url(),
      errorText: request.failure()?.errorText ?? 'unknown',
      firstPartyOrigins,
    })
    if (failure !== null) requestFailures.push(`${request.method()} ${failure}`)
  })
  page.on('pageerror', (error) => pageErrors.push(String(error.message)))
}

/** Ask the page what it shows until it has settled. */
async function settled(page, read, argument) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const state = await page.evaluate(read, argument)
    if (state !== null) return state
    await page.waitForTimeout(25)
  }
  return { outcome: 'timeout', rows: 0 }
}

/** A page with one table: rows, an empty table, or the page's error text. */
function tableState(errorText) {
  if (document.body.innerText.includes(errorText)) return { outcome: 'error', rows: 0 }
  const body = document.querySelector('table tbody')
  if (body === null) return null
  return { outcome: body.children.length > 0 ? 'rows' : 'empty', rows: body.children.length }
}

async function act(tab, action, service, run) {
  const startedAt = Date.now()
  let result
  try {
    result = await run()
  } catch (error) {
    result = { outcome: 'exception', rows: 0, detail: String(error.message).slice(0, 200) }
  }
  actions.push({ tab, action, service, ms: Date.now() - startedAt, ...result })
  return result
}

/** Load a page and wait for the one API answer it is built from. */
async function answered(page, url, apiPath) {
  const [response] = await Promise.all([
    page.waitForResponse((item) => new URL(item.url()).pathname === apiPath, { timeout }),
    page.goto(url, { waitUntil: 'domcontentloaded', timeout }),
  ])
  if (!response.ok() && response.status() !== 404) {
    return { outcome: 'error', rows: 0, detail: `status ${response.status()}` }
  }
  return { outcome: 'answered', rows: 0 }
}

async function browse(context, tab, deadline) {
  const page = await context.newPage()
  record(page)
  let turn = tab
  while (Date.now() < deadline) {
    const service = services[turn % services.length]
    turn += 1

    // The page a person lands on.
    await act(tab, 'services', service, async () => {
      await page.goto(`${studioOrigin}/logs`, { waitUntil: 'domcontentloaded', timeout })
      return settled(
        page,
        ([errorText, name]) => {
          const text = document.body.innerText
          if (text.includes(errorText)) return { outcome: 'error', rows: 0 }
          return text.includes(name) ? { outcome: 'rows', rows: 1 } : null
        },
        [SERVICES_ERROR, service],
      )
    })
    if (Date.now() >= deadline) break

    // The Traces page as it opens: "Has LLM Spans" is checked.
    await act(tab, 'traces, default view', service, async () => {
      await page.goto(`${studioOrigin}/traces/${encodeURIComponent(service)}`, {
        waitUntil: 'domcontentloaded',
        timeout,
      })
      return settled(page, tableState, TRACES_ERROR)
    })
    if (Date.now() >= deadline) break

    // Every trace: the person clears the filter. The default view's table
    // stays on the page for a moment, so the new list's answer is awaited
    // before the page is read.
    const allTraces = await act(tab, 'traces, all', service, async () => {
      await Promise.all([
        page.waitForResponse(
          (item) => {
            const url = new URL(item.url())
            return url.pathname.endsWith('/spans/root') && !url.searchParams.has('has_llm')
          },
          { timeout },
        ),
        page.getByRole('checkbox').uncheck({ timeout }),
      ])
      return settled(page, tableState, TRACES_ERROR)
    })
    if (Date.now() >= deadline) break

    // One key's traces: the person picks the first key in the picker.
    if (values['api-key-filter']) {
      await act(tab, 'traces, one key', service, async () => {
        await Promise.all([
          page.waitForResponse(
            (item) => {
              const url = new URL(item.url())
              return url.pathname.endsWith('/spans/root') && url.searchParams.has('api_key_id')
            },
            { timeout },
          ),
          page.getByRole('combobox').selectOption({ index: 1 }, { timeout }),
        ])
        return settled(page, tableState, TRACES_ERROR)
      })
      if (Date.now() >= deadline) break
      // Back to every key, so the next step opens a trace of the full list.
      await Promise.all([
        page.waitForResponse(
          (item) => {
            const url = new URL(item.url())
            return url.pathname.endsWith('/spans/root') && !url.searchParams.has('api_key_id')
          },
          { timeout },
        ),
        page.getByRole('combobox').selectOption({ index: 0 }, { timeout }),
      ])
      await settled(page, tableState, TRACES_ERROR)
    }

    // Open one trace of the list, a different row each time.
    if (allTraces.outcome === 'rows') {
      await act(tab, 'trace detail', service, async () => {
        const row = page.locator('table tbody tr').nth((turn * 7) % allTraces.rows)
        const [response] = await Promise.all([
          page.waitForResponse((item) => new URL(item.url()).pathname.startsWith('/api/v1/trace-evidence/'), {
            timeout,
          }),
          row.click({ timeout }),
        ])
        if (!response.ok()) return { outcome: 'error', rows: 0, detail: `status ${response.status()}` }
        return settled(
          page,
          ([errorText, emptyText, loadingText]) => {
            const text = document.body.innerText
            if (text.includes(errorText)) return { outcome: 'error', rows: 0 }
            if (text.includes(emptyText)) return { outcome: 'empty', rows: 0 }
            return text.includes(loadingText) ? null : { outcome: 'rows', rows: 1 }
          },
          [TRACE_DETAIL_ERROR, TRACE_DETAIL_EMPTY, LOADING],
        )
      })
    }
    if (Date.now() >= deadline) break

    // The Workflow executions of the service.
    await act(tab, 'workflows', service, async () => {
      await page.goto(`${studioOrigin}/logs/${encodeURIComponent(service)}`, {
        waitUntil: 'domcontentloaded',
        timeout,
      })
      return settled(page, tableState, WORKFLOWS_ERROR)
    })
    if (!values['history-pages'] || Date.now() >= deadline) continue

    // The Agent executions of the service. The backend reads every Agent
    // span the service ever sent to answer one page.
    await act(tab, 'agents', service, async () => {
      const url = new URL('/agents', studioOrigin)
      url.searchParams.set('service_name', service)
      return answered(page, url.href, '/api/v1/agent-executions')
    })
    if (Date.now() >= deadline) break

    // A deep link to one execution by its runtime identity. The backend
    // reads every executable span of the service to find it. No execution
    // has this identity, so the answer is that there is none.
    await act(tab, 'execution link', service, async () => {
      const url = new URL('/resolve/executable', studioOrigin)
      url.searchParams.set('service_namespace', '')
      url.searchParams.set('service_name', service)
      url.searchParams.set('executable_type', 'workflow')
      url.searchParams.set('runtime_id', `live-load-${tab}-${turn}`)
      url.searchParams.set('destination', 'detail')
      return answered(page, url.href, '/api/v1/execution-resolution')
    })
  }
  await page.close()
}

const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
  const page = await context.newPage()
  await page.goto(`${studioOrigin}/sign-in`, { waitUntil: 'domcontentloaded', timeout })
  await page.getByPlaceholder('Email address').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForFunction(() => window.location.pathname !== '/sign-in', undefined, { timeout })
  await page.close()

  const deadline = Date.now() + durationMilliseconds
  await Promise.all(Array.from({ length: tabs }, (_, tab) => browse(context, tab, deadline)))
} finally {
  await browser.close()
}

await writeFile(values.output, JSON.stringify({ tabs, services, actions, responses, requestFailures, pageErrors }))
console.log(
  `${actions.length} page loads, ${responses.length} API responses, ` +
    `${responses.filter((response) => response.status >= 500).length} of them 5xx`,
)
