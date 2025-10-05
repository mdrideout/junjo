import JSONView from '@uiw/react-json-view'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { lightTheme } from '@uiw/react-json-view/light'
import { useEffect, useState } from 'react'

interface SpanAttributeKeyValueViewerProps {
  value: any
}

function tryParseJson(value: string) {
  try {
    const parsed = JSON.parse(value)
    return { success: true, result: parsed }
  } catch (e) {
    return { success: false, result: null }
  }
}

export default function SpanAttributeKeyValueViewer({ value }: SpanAttributeKeyValueViewerProps) {
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setPrefersDarkMode(mediaQuery.matches)

    const listener = (event: MediaQueryListEvent) => {
      setPrefersDarkMode(event.matches)
    }

    mediaQuery.addEventListener('change', listener)
    return () => mediaQuery.removeEventListener('change', listener)
  }, [])

  const displayTheme = prefersDarkMode ? vscodeTheme : lightTheme

  if (typeof value === 'string') {
    const parsedJson = tryParseJson(value)
    if (parsedJson.success) {
      return (
        <JSONView
          value={parsedJson.result}
          displayDataTypes={false}
          style={{ ...displayTheme, fontFamily: 'var(--font-mono)', backgroundColor: 'transparent' }}
        />
      )
    }
  }

  if (typeof value === 'object' && value !== null) {
    return (
      <JSONView
        value={value}
        displayDataTypes={false}
        style={{ ...displayTheme, fontFamily: 'var(--font-mono)', backgroundColor: 'transparent' }}
      />
    )
  }

  return (
    <div className="font-mono text-xs whitespace-pre-wrap">{value === null ? 'null' : String(value)}</div>
  )
}
