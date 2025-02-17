import { useActionData, useFetcher } from 'react-router'
import TextCopyButton from '~/components/text-copy-button'
import type { HashPasswordResponse } from '~/routes/api/hash-password'

interface ActionData {
  hashedPassword: string
  error?: string
}

export default function PasswordHashingForm() {
  const actionData = useActionData<ActionData>()
  const fetcher = useFetcher<HashPasswordResponse>()

  // Results
  const error = fetcher.data?.error
  const loading = fetcher.state === 'loading'
  const hashedPassword = fetcher.data?.hashedPassword

  return (
    <div>
      <h4 className="font-sans">Password Hashing Form</h4>
      <p className={'mb-2'}>
        <i>Remove for production.</i>
      </p>
      <p>Create hashes of passwords to utilize inside the users-db.json file.</p>
      <fetcher.Form method="post" action="/api/hash-password" className="mb-2">
        <label>
          Password:
          <input type="password" name="password" required className="mx-1" />
        </label>
        <button type="submit" className="bg-gray-200 hover:bg-gray-300 m-1 px-2 rounded-md cursor-pointer">
          Hash Password
        </button>
      </fetcher.Form>
      {error && <p className="text-red-700">{error}</p>}
      {loading && <p>Loading...</p>}

      {hashedPassword && (
        <div>
          <div className="font-bold flex gap-x-1 items-center">
            <div>Hashed Password:</div>
            <TextCopyButton textToCopy={hashedPassword} />
          </div>
          <p>{hashedPassword}</p>
        </div>
      )}
    </div>
  )
}
