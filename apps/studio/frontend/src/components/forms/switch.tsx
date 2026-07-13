import { Switch as BaseSwitch } from '@base-ui/react/switch'
import { useId } from 'react'

export interface SwitchProps {
  checked: boolean
  disabled?: boolean
  label: string
  description?: string
  name?: string
  onCheckedChange: (checked: boolean) => void
  required?: boolean
  value?: string
}

/** A controlled, labelled boolean setting. */
export function Switch({
  checked,
  disabled = false,
  label,
  description,
  name,
  onCheckedChange,
  required = false,
  value,
}: SwitchProps) {
  const generatedId = useId()
  const inputId = `studio-switch-${generatedId}`
  const labelId = `${inputId}-label`
  const descriptionId = description ? `${inputId}-description` : undefined

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <label
          id={labelId}
          htmlFor={inputId}
          className="block cursor-pointer text-sm font-medium text-[var(--studio-text)]"
        >
          {label}
        </label>
        {description && (
          <p id={descriptionId} className="mt-0.5 text-xs text-[var(--studio-text-muted)]">
            {description}
          </p>
        )}
      </div>
      <BaseSwitch.Root
        id={inputId}
        aria-labelledby={labelId}
        aria-describedby={descriptionId}
        checked={checked}
        disabled={disabled}
        name={name}
        onCheckedChange={onCheckedChange}
        required={required}
        value={value}
        className={
          'relative h-6 w-11 shrink-0 cursor-pointer rounded-full border border-transparent ' +
          'bg-[var(--studio-switch-off)] transition-colors outline-none ' +
          'data-[checked]:bg-[var(--studio-switch-on)] data-[disabled]:cursor-not-allowed data-[disabled]:opacity-45 ' +
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'
        }
      >
        <BaseSwitch.Thumb
          className={
            'block size-5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform ' +
            'data-[checked]:translate-x-[1.375rem]'
          }
        />
      </BaseSwitch.Root>
    </div>
  )
}
