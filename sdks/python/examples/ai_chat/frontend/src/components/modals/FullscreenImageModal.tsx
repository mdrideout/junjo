import { useEffect } from 'react'

interface FullscreenImageModalProps {
  src: string
  alt: string
  onClose: () => void
}

export default function FullscreenImageModal({ src, alt, onClose }: FullscreenImageModalProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="relative" onClick={(event) => event.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 w-10 h-10 rounded-full bg-zinc-900/80 hover:bg-zinc-800 text-zinc-100 text-3xl leading-none cursor-pointer"
          aria-label="Close"
        >
          &times;
        </button>
        <img src={src} alt={alt} className="max-w-[95vw] max-h-[90vh] object-contain rounded-2xl" />
      </div>
    </div>
  )
}
