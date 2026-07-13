import { ActionButton } from '../../../components/actions/action-button'
import { AppLink } from '../../../components/navigation/app-link'
import { Modal, ModalFooter } from '../../../components/overlays/modal'
import { ProviderWarning } from '../utils/provider-warnings'

interface ProviderWarningModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  warning: ProviderWarning
}

export default function ProviderWarningModal({ open, onOpenChange, warning }: ProviderWarningModalProps) {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="wide"
      title={warning.title}
      description={warning.description}
    >
      <div className="space-y-4">
        {warning.learnMoreUrl && (
          <div className="pb-2 text-sm">
            <AppLink href={warning.learnMoreUrl} newTab>
              Learn more about structured output →
            </AppLink>
          </div>
        )}

        <div>
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-2">Current Approach</h3>
          <pre className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-md overflow-x-auto text-xs">
            <code className="text-zinc-800 dark:text-zinc-200">{warning.codeExampleBad}</code>
          </pre>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-2">
            Recommended Approach
          </h3>
          <pre className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-md overflow-x-auto text-xs">
            <code className="text-zinc-800 dark:text-zinc-200">{warning.codeExampleGood}</code>
          </pre>
        </div>
      </div>

      <ModalFooter>
        <ActionButton onClick={() => onOpenChange(false)}>Close</ActionButton>
      </ModalFooter>
    </Modal>
  )
}
