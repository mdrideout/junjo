import { configureStore } from '@reduxjs/toolkit'
import { render, screen } from '@testing-library/react'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { OtelSpan } from '../../traces/schemas/schemas'
import workflowDetailSlice from '../workflow-detail/store/slice'
import WorkflowListRow from './WorkflowListItem'

function createWorkflowSpan(attributes: Record<string, unknown> = {}): OtelSpan {
  return {
    trace_id: '11111111111111111111111111111111',
    span_id: '2222222222222222',
    parent_span_id: null,
    service_name: 'test-service',
    name: 'Test Workflow',
    kind: 'SERVER',
    start_time: '2026-06-21T20:00:00.000000+00:00',
    end_time: '2026-06-21T20:00:01.000000+00:00',
    status_code: '0',
    status_message: '',
    attributes_json: {
      'junjo.span_type': 'workflow',
      'junjo.workflow.node.count': 1,
      ...attributes,
    },
    events_json: [],
    links_json: [],
    trace_flags: 0,
    trace_state: null,
  }
}

function renderWorkflowListRow(workflowSpan: OtelSpan) {
  const store = configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
    },
  })

  return render(
    <Provider store={store}>
      <BrowserRouter>
        <table>
          <tbody>
            <WorkflowListRow workflowSpan={workflowSpan} />
          </tbody>
        </table>
      </BrowserRouter>
    </Provider>,
  )
}

describe('WorkflowListRow', () => {
  it('renders the failure icon from the workflow span data without trace detail state', () => {
    renderWorkflowListRow(createWorkflowSpan({ 'error.type': 'RuntimeError' }))

    expect(screen.getByLabelText('Workflow execution failed')).toBeInTheDocument()
  })

  it('does not render the failure icon for a successful workflow span', () => {
    renderWorkflowListRow(createWorkflowSpan())

    expect(screen.queryByLabelText('Workflow execution failed')).not.toBeInTheDocument()
  })
})
