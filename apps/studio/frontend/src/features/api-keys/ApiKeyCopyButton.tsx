import { CopyIcon } from '@radix-ui/react-icons'
import { useRef } from 'react'

interface ApiKeyCopyButtonProps {
  apiKey: string
}

export default function ApiKeyCopyButton(props: ApiKeyCopyButtonProps) {
  const { apiKey } = props
  const buttonRef = useRef<HTMLButtonElement>(null)

  const handleCopy = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key)
      const btn = buttonRef.current
      if (btn) {
        btn.classList.add('bg-green-300', 'dark:bg-green-700')
        // after 1s, remove the class to fade back
        setTimeout(() => {
          btn.classList.remove('bg-green-300', 'dark:bg-green-700')
        }, 1000)
      }
    } catch (err) {
      console.error('Failed to copy:', err)
      alert(`Failed to copy API key to clipboard. ${err}`)
    }
  }

  return (
    <button
      ref={buttonRef}
      onClick={() => handleCopy(apiKey)}
      className="p-1 rounded-md cursor-pointer transition-colors duration-300 ease-out"
    >
      <CopyIcon className="size-4" />
    </button>
  )
}
