import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ActionButton } from '../actions/action-button'
import { Modal, ModalFooter } from './modal'

function ModalHarness({ onSubmit = vi.fn() }: { onSubmit?: () => void }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open preferences
      </button>
      <Modal open={open} onOpenChange={setOpen} title="Preferences" description="Choose how Studio behaves.">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <label>
            Display name
            <input name="displayName" />
          </label>
          <ModalFooter>
            <ActionButton intent="secondary" onClick={() => setOpen(false)}>
              Cancel
            </ActionButton>
            <ActionButton type="submit">Save</ActionButton>
          </ModalFooter>
        </form>
      </Modal>
    </>
  )
}

describe('Modal', () => {
  it('provides an accessible dialog, traps focus, and submits explicit actions', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ModalHarness onSubmit={onSubmit} />)

    const opener = screen.getByRole('button', { name: 'Open preferences' })
    await user.click(opener)

    const dialog = await screen.findByRole('dialog', { name: 'Preferences' })
    expect(dialog).toHaveAccessibleDescription('Choose how Studio behaves.')

    const input = within(dialog).getByRole('textbox', { name: 'Display name' })
    await waitFor(() => expect(input).toHaveFocus())

    await user.tab({ shift: true })
    expect(opener).not.toHaveFocus()
    expect(dialog).toBeInTheDocument()
    const closeButton = within(dialog).getByRole('button', { name: 'Close dialog' })
    await waitFor(() => expect(closeButton).toHaveFocus())
    await user.tab()
    expect(opener).not.toHaveFocus()
    expect(dialog).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('dismisses with Escape and restores focus to the opener', async () => {
    const user = userEvent.setup()
    render(<ModalHarness />)

    const opener = screen.getByRole('button', { name: 'Open preferences' })
    await user.click(opener)
    await screen.findByRole('dialog', { name: 'Preferences' })

    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Preferences' })).not.toBeInTheDocument()
    })
    expect(opener).toHaveFocus()
  })

  it('dismisses when the user presses outside the popup', async () => {
    const user = userEvent.setup()
    render(<ModalHarness />)

    await user.click(screen.getByRole('button', { name: 'Open preferences' }))
    await screen.findByRole('dialog', { name: 'Preferences' })

    await user.click(document.body)

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Preferences' })).not.toBeInTheDocument()
    })
  })
})
