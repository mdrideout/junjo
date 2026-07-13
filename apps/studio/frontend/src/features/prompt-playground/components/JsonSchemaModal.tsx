import { useEffect, useState } from 'react'
import { ActionButton } from '../../../components/actions/action-button'
import { Modal, ModalFooter } from '../../../components/overlays/modal'
import { JsonSchemaInfo } from '../utils/provider-warnings'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { TriangleDownIcon } from '@radix-ui/react-icons'

interface JsonSchemaModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  schemaInfo: JsonSchemaInfo
}

export default function JsonSchemaModal({ open, onOpenChange, schemaInfo }: JsonSchemaModalProps) {
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // JSON Renderer Theme Decider
  const displayTheme = prefersDarkMode ? vscodeTheme : lightTheme

  // Detect preferred color scheme
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setPrefersDarkMode(mediaQuery.matches)

    const listener = (event: MediaQueryListEvent) => {
      setPrefersDarkMode(event.matches)
    }

    mediaQuery.addEventListener('change', listener)
    return () => mediaQuery.removeEventListener('change', listener)
  }, [])

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="wide"
      title="Response JSON Schema Used"
      description="This LLM request used a JSON schema to structure the response. The schema below was captured in telemetry from the invocation parameters."
    >
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-2">JSON Schema</h3>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded-md overflow-hidden max-h-96 overflow-y-auto">
            <JsonView
              key={JSON.stringify(schemaInfo.schema)}
              value={schemaInfo.schema}
              collapsed={false}
              style={{ ...displayTheme, fontFamily: 'var(--font-mono)' }}
            >
              {/* Zero width whitespace char */}
              <JsonView.Quote>&#8203;</JsonView.Quote>
              <JsonView.Arrow>
                <TriangleDownIcon className={'size-4 leading-0'} />
              </JsonView.Arrow>
            </JsonView>
          </div>
        </div>
      </div>

      <ModalFooter>
        <ActionButton onClick={() => onOpenChange(false)}>Close</ActionButton>
      </ModalFooter>
    </Modal>
  )
}
