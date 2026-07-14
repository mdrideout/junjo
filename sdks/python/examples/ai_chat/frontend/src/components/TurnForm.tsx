import { useState, type FormEvent } from 'react'
import { MAX_TURN_TEXT_LENGTH } from '../api/schemas'

interface TurnFormProps {
  disabled: boolean
  sending: boolean
  onSubmit: (text: string) => Promise<boolean>
}

export function TurnForm({ disabled, sending, onSubmit }: TurnFormProps) {
  const [text, setText] = useState('')

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!text.trim()) return
    if (await onSubmit(text)) setText('')
  }

  return (
    <form className="turn-form" onSubmit={submit}>
      <label htmlFor="turn-text">Message</label>
      <div className="turn-controls">
        <textarea
          id="turn-text"
          name="text"
          rows={2}
          maxLength={MAX_TURN_TEXT_LENGTH}
          value={text}
          disabled={disabled || sending}
          placeholder="Ask the Agent to help…"
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" disabled={disabled || sending || !text.trim()}>
          {sending ? 'Running…' : 'Send'}
        </button>
      </div>
      <p>The response is returned synchronously with Workflow and Agent evidence IDs.</p>
    </form>
  )
}
