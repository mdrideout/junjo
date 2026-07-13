import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { Switch } from './switch'

beforeAll(() => {
  if (!window.PointerEvent) {
    Object.defineProperty(window, 'PointerEvent', {
      configurable: true,
      value: MouseEvent,
    })
  }
})

function ControlledSwitch({
  disabled = false,
  onCheckedChange,
}: {
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  const [checked, setChecked] = useState(false)

  return (
    <Switch
      label="Structured output"
      description="Require a JSON response."
      checked={checked}
      disabled={disabled}
      onCheckedChange={(nextChecked) => {
        setChecked(nextChecked)
        onCheckedChange(nextChecked)
      }}
    />
  )
}

describe('Switch', () => {
  it('is labelled and responds to its label and keyboard', async () => {
    const user = userEvent.setup()
    const onCheckedChange = vi.fn()

    render(<ControlledSwitch onCheckedChange={onCheckedChange} />)

    const toggle = screen.getByRole('switch', { name: 'Structured output' })
    expect(toggle).toHaveAccessibleDescription('Require a JSON response.')
    expect(toggle).toHaveAttribute('aria-checked', 'false')

    await user.click(screen.getByText('Structured output'))
    expect(onCheckedChange).toHaveBeenLastCalledWith(true)
    expect(toggle).toHaveAttribute('aria-checked', 'true')

    toggle.focus()
    await user.keyboard(' ')
    expect(onCheckedChange).toHaveBeenLastCalledWith(false)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('ignores pointer and keyboard input while disabled', async () => {
    const user = userEvent.setup()
    const onCheckedChange = vi.fn()

    render(<ControlledSwitch disabled onCheckedChange={onCheckedChange} />)

    const toggle = screen.getByRole('switch', { name: 'Structured output' })
    await user.click(screen.getByText('Structured output'))
    toggle.focus()
    await user.keyboard(' ')

    expect(onCheckedChange).not.toHaveBeenCalled()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })
})
