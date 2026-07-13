import { useNavigate } from 'react-router'
import useCreateAndUpsertContact from '../../api/contact/hooks/create-upsert-contact-hook'
import { Sex } from '../../api/contact/schemas'

export default function NewContactButton() {
  const navigate = useNavigate()
  const { isLoading, error, createContact } = useCreateAndUpsertContact()

  async function handleOnClick(sex: Sex) {
    try {
      const chat_id = await createContact(sex)
      navigate(`/${chat_id}`)
    } catch (e) {
      // do nothing
    }
  }

  return (
    <div className="flex flex-col gap-y-2">
      <button
        disabled={isLoading}
        onClick={() => handleOnClick(Sex.MALE)}
        className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-blue-300 rounded-2xl bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 disabled:opacity-60 text-white leading-none px-3 py-5"
      >
        <div>{error ? 'Error, Try Again' : 'New Male'}</div>
        <div className={`${isLoading ? 'animate-rotate' : ''}`}>
          <span aria-hidden="true">🙋‍♂️</span>
        </div>
      </button>

      <button
        disabled={isLoading}
        onClick={() => handleOnClick(Sex.FEMALE)}
        className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-pink-300 rounded-2xl bg-gradient-to-b from-pink-600 to-pink-700 hover:to-pink-800 disabled:opacity-60 text-white leading-none px-3 py-5"
      >
        <div>{error ? 'Error, Try Again' : 'New Female'}</div>
        <div className={`${isLoading ? 'animate-rotate' : ''}`}>
          <span aria-hidden="true">🙋‍♀️</span>
        </div>
      </button>
    </div>
  )
}
