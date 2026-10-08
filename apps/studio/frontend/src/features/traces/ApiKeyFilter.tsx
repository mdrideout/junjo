import { useEffect, useState } from 'react'
import { fetchApiKeys } from '../api-keys/fetch/list-api-keys'
import type { ApiKey } from '../api-keys/schemas'

interface ApiKeyFilterProps {
  /** The selected key's identifier, or an empty string for every key. */
  apiKeyId: string
  onChange: (apiKeyId: string) => void
}

/**
 * Chooses the API key whose traces a listing shows. Ingestion records which
 * key sent each span. Deleted keys are not offered: their traces stay in the
 * listing of every key.
 */
export default function ApiKeyFilter({ apiKeyId, onChange }: ApiKeyFilterProps) {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])

  useEffect(() => {
    let current = true
    fetchApiKeys()
      .then((keys) => {
        if (current) setApiKeys(keys)
      })
      .catch(() => {
        // Without the keys the listing still shows every key's traces.
      })
    return () => {
      current = false
    }
  }, [])

  return (
    <label className="inline-flex items-center">
      <span className="mr-2 text-sm">API key</span>
      <select
        className="rounded border border-zinc-300 bg-transparent px-2 py-1 text-sm"
        value={apiKeyId}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">All API keys</option>
        {apiKeys.map((apiKey) => (
          <option key={apiKey.id} value={apiKey.id}>
            {apiKey.name}
          </option>
        ))}
      </select>
    </label>
  )
}
