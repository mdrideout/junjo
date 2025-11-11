import { Button } from '../../../components/catalyst/button'
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../../components/catalyst/dialog'
import { ProviderWarning } from '../utils/provider-warnings'

interface ProviderWarningModalProps {
  isOpen: boolean
  onClose: () => void
  warning: ProviderWarning
}

export default function ProviderWarningModal({ isOpen, onClose, warning }: ProviderWarningModalProps) {
  return (
    <Dialog open={isOpen} onClose={onClose} size="4xl">
      <DialogTitle>{warning.title}</DialogTitle>
      <DialogDescription>{warning.description}</DialogDescription>
      <DialogBody>
        <div className="space-y-4">
          {warning.learnMoreUrl && (
            <div className="pb-2">
              <a
                href={warning.learnMoreUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                Learn more about structured output →
              </a>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-2">Current Approach</h3>
            <pre className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-md overflow-x-auto text-xs">
              <code className="text-zinc-800 dark:text-zinc-200">{warning.codeExampleBad}</code>
            </pre>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-2">Recommended Approach</h3>
            <pre className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-md overflow-x-auto text-xs">
              <code className="text-zinc-800 dark:text-zinc-200">{warning.codeExampleGood}</code>
            </pre>
          </div>
        </div>

        <DialogActions>
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </DialogBody>
    </Dialog>
  )
}
