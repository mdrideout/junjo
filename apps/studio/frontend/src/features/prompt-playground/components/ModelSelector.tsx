import * as Select from '@radix-ui/react-select'
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from '@radix-ui/react-icons'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { PromptPlaygroundActions } from '../store/slice'
import { forwardRef } from 'react'
import clsx from 'clsx'

// Hardcoded list of models for now
const DEFAULT_MODELS = [
  'gemini-2.5-flash',
  'gemini-2.5-flash-lite',
  'gemini-2.5-pro',
  'gemini-2.0-flash',
  'gemini-2.0-flash-lite',
]

interface ModelSelectorProps {
  originalModel: string | null
}

export default function ModelSelector(props: ModelSelectorProps) {
  const { originalModel } = props
  const dispatch = useAppDispatch()
  const selectedModel = useAppSelector((state) => state.promptPlaygroundState.selectedModel)

  const selectableModels = originalModel ? [...DEFAULT_MODELS, originalModel] : DEFAULT_MODELS

  const handleValueChange = (value: string) => {
    dispatch(PromptPlaygroundActions.setSelectedModel(value))
  }

  return (
    <Select.Root value={selectedModel ?? undefined} onValueChange={handleValueChange}>
      <Select.Trigger
        className="inline-flex items-center justify-center rounded px-[15px] text-[13px] leading-none h-[35px] gap-[5px] bg-white text-gray-900 shadow-[0_2px_10px] shadow-black/10 hover:bg-gray-100 focus:shadow-[0_0_0_2px] focus:shadow-black data-[placeholder]:text-gray-500 outline-none"
        aria-label="Model"
      >
        <Select.Value placeholder="Select a model…" />
        <Select.Icon className="text-gray-900">
          <ChevronDownIcon />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="overflow-hidden bg-white rounded-md shadow-[0px_10px_38px_-10px_rgba(22,_23,_24,_0.35),0px_10px_20px_-15px_rgba(22,_23,_24,_0.2)]">
          <Select.ScrollUpButton className="flex items-center justify-center h-[25px] bg-white text-gray-900 cursor-default">
            <ChevronUpIcon />
          </Select.ScrollUpButton>
          <Select.Viewport className="p-[5px]">
            <Select.Group>
              {selectableModels.map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </Select.Group>
          </Select.Viewport>
          <Select.ScrollDownButton className="flex items-center justify-center h-[25px] bg-white text-gray-900 cursor-default">
            <ChevronDownIcon />
          </Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  )
}

const SelectItem = forwardRef<
  HTMLDivElement,
  { children: React.ReactNode; className?: string; value: string }
>(({ children, className, ...props }, forwardedRef) => {
  return (
    <Select.Item
      className={clsx(
        'text-[13px] leading-none text-gray-900 rounded-[3px] flex items-center h-[25px] pr-[35px] pl-[25px] relative select-none data-[disabled]:text-gray-400 data-[disabled]:pointer-events-none data-[highlighted]:outline-none data-[highlighted]:bg-blue-500 data-[highlighted]:text-white',
        className,
      )}
      {...props}
      ref={forwardedRef}
    >
      <Select.ItemText>{children}</Select.ItemText>
      <Select.ItemIndicator className="absolute left-0 w-[25px] inline-flex items-center justify-center text-inherit">
        <CheckIcon />
      </Select.ItemIndicator>
    </Select.Item>
  )
})
