import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { expect, it } from 'vitest'
import type { RootState } from '../../../root-store/store'
import { TraceEvidenceSchema } from '../../traces/schemas/trace-evidence'
import { hydrateStoreView } from '../../store-diagnostics/hydrate-store-view'
import { selectAgentExecutionDetailRequest } from '../store/selectors'
import { AgentExecutionDetailView } from '../components/AgentExecutionDetailView'
import { agentPath, tracesPath } from '../../../util/telemetry-paths'

it('hydrates both Store views and navigates from their transitions to the actual writer spans', async () => {
  const artifact = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
    '../../../../../backend/tests/generated/composable_store_trace.json')
  const evidence = TraceEvidenceSchema.parse(JSON.parse(fs.readFileSync(artifact, 'utf8')))
  const agent = Object.values(evidence.executables_by_span_id).find((item) => item.executable_type === 'agent')!
  const workflow = Object.values(evidence.executables_by_span_id).find((item) => item.executable_type === 'workflow')!
  const app = agent.stores.application!
  const child = workflow.stores.application!
  expect(app.store_id).toBe(child.store_id)
  expect(app.store_id).not.toBe(agent.stores.runtime!.store_id)
  const events = evidence.stores_by_id[app.store_id!].transitions
  expect(events).toHaveLength(3)
  expect(hydrateStoreView(child, events)?.transitions.map((item) => item.sequence)).toEqual([4])
  const state = { tracesState: { traceEvidence: { [evidence.trace_id]: evidence },
    traceEvidenceRequest: { traceId: evidence.trace_id, loading: false, error: false } } } as RootState
  const detail = selectAgentExecutionDetailRequest(state, { traceId: evidence.trace_id, agentSpanId: agent.owner_span_id }).data!
  expect(detail.application_state.transitions).toHaveLength(3)
  expect(detail.state.store_id).toBe(agent.stores.runtime!.store_id)
  const router = createMemoryRouter([{ path: '*', element: <AgentExecutionDetailView detail={detail} /> }], {
    initialEntries: [agentPath(detail.summary.trace_id, detail.summary.agent_span_id)],
  })
  render(<RouterProvider router={router} />)
  for (const [name, state] of [
    ['Application state history', detail.application_state],
    ['Agent runtime state history', detail.state],
  ] as const) {
    const region = within(screen.getByRole('region', { name }))
    const transition = state.transitions[0]
    await userEvent.click(region.getByRole('button', {
      name: `${transition.sequence}. ${transition.action} revision ${transition.revision_before} → ${transition.revision_after}`,
    }))
    const writer = region.getByRole('link', { name: /View writer span/ })
    const destination = tracesPath(detail.summary.service.name, detail.summary.trace_id, transition.span_id)
    expect(writer).toHaveAttribute('href', destination)
    await userEvent.click(writer)
    expect(router.state.location.pathname).toBe(destination)
  }
})
