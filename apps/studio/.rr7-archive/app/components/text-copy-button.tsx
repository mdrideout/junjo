interface TextCopyButtonProps {
  textToCopy: string
}

const handleCopy = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
  } catch (err) {
    console.error('Error copying text:', err)
  }
}

export default function TextCopyButton({ textToCopy }: TextCopyButtonProps) {
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          handleCopy(textToCopy)
        }}
        className="bg-gray-200 hover:bg-gray-300 px-2 text-xs rounded-md cursor-pointer"
      >
        Copy
      </button>
    </div>
  )
}
