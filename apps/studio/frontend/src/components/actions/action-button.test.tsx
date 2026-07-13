import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ActionButton } from './action-button'

describe('ActionButton', () => {
  it('does not submit a form unless submission is explicit', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault())

    render(
      <form onSubmit={onSubmit}>
        <ActionButton>Secondary action</ActionButton>
        <ActionButton type="submit">Save</ActionButton>
      </form>,
    )

    await user.click(screen.getByRole('button', { name: 'Secondary action' }))
    expect(onSubmit).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('does not invoke disabled actions', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()

    render(
      <ActionButton disabled onClick={onClick}>
        Delete
      </ActionButton>,
    )

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onClick).not.toHaveBeenCalled()
  })
})
