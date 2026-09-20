import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SpanAttributeKeyValueViewer from './SpanAttributeKeyValueViewer'

describe('SpanAttributeKeyValueViewer', () => {
  it.each(['object', 'serialized JSON'])('shows explicit nested null values in %s evidence', (format) => {
    const state = { eligible: null, order: { decision: null }, history: [null], approved: false }
    render(<SpanAttributeKeyValueViewer value={format === 'object' ? state : JSON.stringify(state)} />)

    expect(screen.getAllByText('null', { exact: true })).toHaveLength(3)
    expect(screen.getByText('false', { exact: true })).toBeVisible()
  })
})
