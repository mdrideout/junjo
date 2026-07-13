import * as Select from '@radix-ui/react-select'
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from '@radix-ui/react-icons'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { PromptPlaygroundActions } from '../store/slice'
import { forwardRef, useMemo } from 'react'
import clsx from 'clsx'
import { getProviderDisplayName } from '../utils/provider-mapping'

// Provider constants
const PROVIDERS = [
  { id: 'gemini', name: 'Google Gemini' },
  { id: 'openai', name: 'OpenAI' },
  { id: 'anthropic', name: 'Anthropic' },
]

interface ProviderSelectorProps {
  originalProvider: string | null
  availableProviders?: string[]
}

export default function ProviderSelector(props: ProviderSelectorProps) {
  const { originalProvider, availableProviders } = props
  const dispatch = useAppDispatch()
  const selectedProvider = useAppSelector((state) => state.promptPlaygroundState.selectedProvider)

  // Build list of selectable providers
  const selectableProviders = useMemo(() => {
    // Start with base providers, filtered by availability if specified
    let providers = PROVIDERS.filter(
      (p) => !availableProviders || availableProviders.includes(p.id),
    )

    // Include original provider if it's not in the list
    // This handles cases where telemetry contains a provider we don't explicitly support
    if (originalProvider && !providers.find((p) => p.id === originalProvider)) {
      providers = [
        ...providers,
        {
          id: originalProvider,
          name: getProviderDisplayName(originalProvider),
        },
      ]
    }

    return providers
  }, [originalProvider, availableProviders])

  const handleValueChange = (value: string) => {
    dispatch(PromptPlaygroundActions.setSelectedProvider(value))
  }

  return (
    <Select.Root value={selectedProvider ?? undefined} onValueChange={handleValueChange}>
      <Select.Trigger
        className="inline-flex items-center justify-center rounded px-[15px] text-[13px] leading-none h-[35px] gap-[5px] bg-white text-gray-900 shadow-[0_2px_10px] shadow-black/10 hover:bg-gray-100 focus:shadow-[0_0_0_2px] focus:shadow-black data-[placeholder]:text-gray-500 outline-none"
        aria-label="Provider"
      >
        <Select.Value placeholder="Select a provider…" />
        <Select.Icon className="text-gray-900">
          <ChevronDownIcon />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="overflow-hidden bg-white rounded-md shadow-[0px_10px_38px_-10px_rgba(22,_23,_24,_0.35),0px_10px_20px_-15px_rgba(22,_23,_24,_0.2)]">
          <Select.ScrollUpButton className="flex items-center justify-center bg-white text-gray-900 cursor-default">
            <ChevronUpIcon />
          </Select.ScrollUpButton>
          <Select.Viewport className="p-[5px]">
            <Select.Group>
              {selectableProviders.map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>
                  {provider.name}
                </SelectItem>
              ))}
            </Select.Group>
          </Select.Viewport>
          <Select.ScrollDownButton className="flex items-center justify-center bg-white text-gray-900 cursor-default">
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
