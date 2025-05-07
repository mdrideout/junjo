import { useNavigate } from 'react-router'
import useCreateAndUpsertContact from '../../api/contact/hooks/create-upsert-contact-hook'
import { PlusCircledIcon } from '@radix-ui/react-icons'

export default function NewContactButton() {
  const navigate = useNavigate()
  const { isLoading, error, createContact } = useCreateAndUpsertContact()

  async function handleOnClick() {
    // Create and upsert the contact
    try {
      const chat_id = await createContact()
      navigate(`/${chat_id}`)
    } catch (e) {
      // do nothing
    }
  }

  return (
    <button
      disabled={isLoading}
      onClick={handleOnClick}
      className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-green-300 rounded-md bg-gradient-to-b from-green-600 to-green-700 hover:to-green-800 disabled:opacity-20 text-white leading-none px-3 py-2"
    >
      <div>{error ? 'Error, Try Again' : 'New Contact'}</div>
      <div className={`${isLoading ? 'animate-rotate' : ''}`}>
        <PlusCircledIcon />
      </div>
    </button>
  )
}
