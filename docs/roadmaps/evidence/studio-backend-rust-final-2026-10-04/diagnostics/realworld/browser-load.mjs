#!/usr/bin/env node
// Drives the real Studio frontend the way a person does, in several tabs,
// for a fixed time, and records what every page showed and what every API
// request answered. It runs while a load generator sends spans to ingestion.
//
// Usage: node browser-load.mjs --studio-url http://127.0.0.1:PORT \
//          --services a,b,c --tabs 4 --duration-seconds 80 --out result.json
// Credentials: JUNJO_STUDIO_E2E_EXISTING_EMAIL / JUNJO_STUDIO_E2E_EXISTING_PASSWORD

import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { parseArgs } from 'node:util'

import { chromium } from '/Users/matt/repos/junjo/apps/studio/frontend/node_modules/playwright/index.mjs'

const { values } = parseArgs({
  options: {
    'studio-url': { type: 'string' },
    services: { type: 'string' },
    tabs: { type: 'string', default: '4' },
    'duration-seconds': { type: 'string', default: '60' },
    out: { type: 'string' },
    'action-timeout-milliseconds': { type: 'string', default: '60000' },
  },
  strict: true,
})
const origin = new URL(values['studio-url']).origin
const services = values.services.split(',')
const tabs = Number.parseInt(values.tabs, 10)
const durationMs = Number.parseInt(values['duration-seconds'], 10) * 1000
const actionTimeout = Number.parseInt(values['action-timeout-milliseconds'], 10)
const email = process.env.JUNJO_STUDIO_E2E_EXISTING_EMAIL
const password = process.env.JUNJO_STUDIO_E2E_EXISTING_PASSWORD
assert.ok(email && password, 'credentials are required in the environment')
assert.ok(values.out, '--out is required')

/** One API route family: identifiers and service names are replaced. */
function family(url) {
  const parsed = new URL(url)
  let path = parsed.pathname
    .replace(/\/services\/[^/]+\//, '/services/{service}/')
    .replace(/\/[0-9a-f]{32}(?=\/|$)/g, '/{trace}')
    .replace(/\/[0-9a-f]{16}(?=\/|$)/g, '/{span}')
  if (parsed.searchParams.get('has_llm') === 'true') path += '?has_llm=true'
  return path
}

const responses = [] // {family, status, ms, at}
const requestFailures = [] // {family, error, at}
const pageErrors = []
const actions = [] // {tab, action, service, at, ms, outcome, rows}

function watch(page) {
  const started = new Map()
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) started.set(request, Date.now())
  })
  page.on('response', (response) => {
    const request = response.request()
    const begin = started.get(request)
    if (begin === undefined) return
    started.delete(request)
    responses.push({ family: family(request.url()), status: response.status(), ms: Date.now() - begin, at: begin })
  })
  page.on('requestfailed', (request) => {
    const begin = started.get(request)
    if (begin === undefined) return
    started.delete(request)
    const error = request.failure()?.errorText ?? 'unknown'
    // A navigation away cancels the previous page's requests. That is the
    // browser, not Studio.
    if (error.includes('ERR_ABORTED')) return
    requestFailures.push({ family: family(request.url()), error, at: begin })
  })
  page.on('pageerror', (error) => pageErrors.push({ message: String(error.message).slice(0, 300), at: Date.now() }))
}

/**
 * Wait until the page shows rows, an error, or an empty table.
 * Returns {outcome, rows}.
 */
async function settle(page, errorText) {
  const deadline = Date.now() + actionTimeout
  while (Date.now() < deadline) {
    const state = await page.evaluate((text) => {
      const body = document.body.innerText
      if (body.includes(text)) return { outcome: 'error', rows: 0 }
      const table = document.querySelector('table tbody')
      if (table !== null) return { outcome: table.children.length > 0 ? 'rows' : 'empty', rows: table.children.length }
      return null
    }, errorText)
    if (state !== null) return state
    await page.waitForTimeout(25)
  }
  return { outcome: 'timeout', rows: 0 }
}

async function act(tab, action, service, run) {
  const at = Date.now()
  let result
  try {
    result = await run()
  } catch (error) {
    result = { outcome: 'exception', rows: 0, detail: String(error.message).slice(0, 200) }
  }
  actions.push({ tab, action, service, at, ms: Date.now() - at, ...result })
  return result
}

async function tabLoop(context, tab, deadline) {
  const page = await context.newPage()
  watch(page)
  let turn = tab
  while (Date.now() < deadline) {
    const service = services[turn % services.length]
    turn += 1

    // The services page a person lands on.
    await act(tab, 'services list', service, async () => {
      await page.goto(`${origin}/logs`, { waitUntil: 'domcontentloaded', timeout: actionTimeout })
      const deadlineAt = Date.now() + actionTimeout
      while (Date.now() < deadlineAt) {
        const state = await page.evaluate((name) => {
          const body = document.body.innerText
          if (body.includes('Error fetching app names.')) return { outcome: 'error', rows: 0 }
          if (body.includes(name)) return { outcome: 'rows', rows: 1 }
          return null
        }, service)
        if (state !== null) return state
        await page.waitForTimeout(25)
      }
      return { outcome: 'timeout', rows: 0 }
    })
    if (Date.now() >= deadline) break

    // The traces page as it opens: "Has LLM Spans" is checked.
    await act(tab, 'traces list, has LLM (default view)', service, async () => {
      await page.goto(`${origin}/traces/${encodeURIComponent(service)}`, {
        waitUntil: 'domcontentloaded',
        timeout: actionTimeout,
      })
      return settle(page, 'Error loading traces.')
    })
    if (Date.now() >= deadline) break

    // Every trace: the person unchecks the filter.
    const all = await act(tab, 'traces list, all', service, async () => {
      await page.getByRole('checkbox').uncheck({ timeout: actionTimeout })
      // The list reloads: wait for the loading text to pass.
      await page.waitForTimeout(50)
      return settle(page, 'Error loading traces.')
    })
    if (Date.now() >= deadline) break

    // Open a trace from the list: a different row each time.
    if (all.outcome === 'rows') {
      await act(tab, 'trace detail', service, async () => {
        const row = page.locator('table tbody tr').nth((turn * 7) % all.rows)
        const [response] = await Promise.all([
          page.waitForResponse((item) => new URL(item.url()).pathname.startsWith('/api/v1/trace-evidence/'), {
            timeout: actionTimeout,
          }),
          row.click({ timeout: actionTimeout }),
        ])
        if (!response.ok()) return { outcome: 'error', rows: 0, detail: `status ${response.status()}` }
        const deadlineAt = Date.now() + actionTimeout
        while (Date.now() < deadlineAt) {
          const state = await page.evaluate(() => {
            const body = document.body.innerText
            if (body.includes('Error loading spans.')) return { outcome: 'error', rows: 0 }
            if (body.includes('No spans found.')) return { outcome: 'empty', rows: 0 }
            if (body.includes('Loading...')) return null
            return { outcome: 'rows', rows: 1 }
          })
          if (state !== null) return state
          await page.waitForTimeout(25)
        }
        return { outcome: 'timeout', rows: 0 }
      })
    }
    if (Date.now() >= deadline) break

    // The Workflow executions of the service.
    await act(tab, 'workflow list', service, async () => {
      await page.goto(`${origin}/logs/${encodeURIComponent(service)}`, {
        waitUntil: 'domcontentloaded',
        timeout: actionTimeout,
      })
      return settle(page, 'Error loading workflow executions')
    })
  }
  await page.close()
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
const startedAt = Date.now()
try {
  const page = await context.newPage()
  await page.goto(`${origin}/sign-in`, { waitUntil: 'domcontentloaded', timeout: actionTimeout })
  await page.getByPlaceholder('Email address').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForFunction(() => window.location.pathname !== '/sign-in', undefined, { timeout: actionTimeout })
  await page.close()

  const deadline = Date.now() + durationMs
  await Promise.all(Array.from({ length: tabs }, (_, tab) => tabLoop(context, tab, deadline)))
} finally {
  await browser.close()
}

await writeFile(
  values.out,
  JSON.stringify({ origin, services, tabs, startedAt, endedAt: Date.now(), actions, responses, requestFailures, pageErrors }),
)
console.log(
  `browser load done: ${actions.length} page actions, ${responses.length} API responses, ` +
    `${responses.filter((item) => item.status >= 500).length} server errors, ${requestFailures.length} failed requests`,
)
