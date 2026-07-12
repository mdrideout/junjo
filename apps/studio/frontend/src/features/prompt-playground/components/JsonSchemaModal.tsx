import { useEffect, useState } from 'react'
import { Button } from '../../../components/catalyst/button'
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../../components/catalyst/dialog'
import { JsonSchemaInfo } from '../utils/provider-warnings'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { TriangleDownIcon } from '@radix-ui/react-icons'

interface JsonSchemaModalProps {
  isOpen: boolean
  onClose: () => void
  schemaInfo: JsonSchemaInfo
}

export default function JsonSchemaModal({ isOpen, onClose, schemaInfo }: JsonSchemaModalProps) {
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
    <Dialog open={isOpen} onClose={onClose} size="4xl">
      <DialogTitle>Response JSON Schema Used</DialogTitle>
      <DialogDescription>
        This LLM request used a JSON schema to structure the response. The schema below was captured in
        telemetry from the invocation parameters.
      </DialogDescription>
      <DialogBody>
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

        <DialogActions>
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </DialogBody>
    </Dialog>
  )
}
