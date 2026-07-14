import assert from 'node:assert/strict'
import test from 'node:test'

import { describeActionableRequestFailure } from './request-failure-policy.mjs'

const firstPartyOrigins = new Set(['http://127.0.0.1:3000', 'http://127.0.0.1:3001'])

test('reports only actionable first-party browser request failures', () => {
  assert.equal(
    describeActionableRequestFailure({
      requestUrl: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono',
      errorText: 'net::ERR_BLOCKED_BY_ORB',
      firstPartyOrigins,
    }),
    null,
  )
  assert.equal(
    describeActionableRequestFailure({
      requestUrl: 'http://127.0.0.1:3001/auth-test',
      errorText: 'net::ERR_ABORTED',
      firstPartyOrigins,
    }),
    null,
  )
  assert.equal(
    describeActionableRequestFailure({
      requestUrl: 'http://127.0.0.1:3001/api/v1/agent-executions',
      errorText: 'net::ERR_CONNECTION_REFUSED',
      firstPartyOrigins,
    }),
    'request failed: http://127.0.0.1:3001/api/v1/agent-executions (net::ERR_CONNECTION_REFUSED)',
  )
})
