import { configureStore } from '@reduxjs/toolkit'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import { OtelSpan, OtelSpanSchema } from '../../traces/schemas/schemas'
import tracesSlice from '../../traces/store/slice'
import workflowDetailSlice from './store/slice'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

function loadFixtureSpans(caseName: string): OtelSpan[] {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  return OtelSpanSchema.array().parse(fixture.spans)
}

function renderStateDiff({
  spans,
  activeSpan,
  defaultWorkflowSpan,
}: {
  spans: OtelSpan[]
  activeSpan: OtelSpan
  defaultWorkflowSpan: OtelSpan
}) {
  const store = configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
      tracesState: tracesSlice,
    },
    preloadedState: {
      workflowDetailState: {
        activeSpan,
        activeSetStateEvent: null,
        scrollToStateEventId: null,
        openFailuresTrigger: null,
      },
      tracesState: {
        serviceNames: {
          data: [],
          loading: false,
          error: false,
        },
        traceSpans: {
          [defaultWorkflowSpan.trace_id]: spans,
        },
        loading: false,
        error: false,
      },
    },
  })

  return render(
    <Provider store={store}>
      <BrowserRouter>
        <WorkflowDetailStateDiff defaultWorkflowSpan={defaultWorkflowSpan} />
      </BrowserRouter>
    </Provider>,
  )
}

describe('WorkflowDetailStateDiff', () => {
  it('keeps state tabs selectable when the active span has no state event', async () => {
    const user = userEvent.setup()
    const spans = loadFixtureSpans('basic_workflow_success')
    const workflowSpan = spans.find((span) => span.span_id === '1111111111111111')

    if (!workflowSpan) {
      throw new Error('Expected basic workflow span in fixture')
    }

    renderStateDiff({
      spans,
      activeSpan: workflowSpan,
      defaultWorkflowSpan: workflowSpan,
    })

    expect(screen.getByText('Basic Information')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Before' }))

    await waitFor(() => {
      expect(screen.queryByText('Basic Information')).not.toBeInTheDocument()
    })
    expect(screen.getByText('input')).toBeInTheDocument()
  })
})
