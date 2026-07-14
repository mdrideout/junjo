import { afterEach, describe, expect, it, vi } from 'vitest'

import { getWorkflowStoreDiagnostic } from './get-workflow-store-diagnostic'

const TRACE_ID = '1'.repeat(32)
const SPAN_ID = 'a'.repeat(16)

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Workflow Store diagnostic errors', () => {
  it('surfaces typed stored-evidence conflicts only at 409', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'unidentifiable_workflow',
      message: 'Workflow evidence is invalid.',
      diagnostics: [{
        code: 'invalid_workflow',
        path: 'workflow.identity',
        message: 'Identity is invalid.',
      }],
    }), { status: 409, headers: { 'Content-Type': 'application/json' } })))

    await expect(getWorkflowStoreDiagnostic(TRACE_ID, SPAN_ID)).rejects.toThrow(
      'unidentifiable_workflow: Workflow evidence is invalid. — invalid_workflow at workflow.identity',
    )
  })

  it('keeps transport validation errors separate at 422', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: [{ type: 'string_pattern_mismatch', loc: ['path', 'trace_id'] }],
    }), { status: 422, headers: { 'Content-Type': 'application/json' } })))

    await expect(getWorkflowStoreDiagnostic(TRACE_ID, SPAN_ID)).rejects.toThrow(
      'Failed to fetch Workflow Store diagnostics (422)',
    )
  })
})
