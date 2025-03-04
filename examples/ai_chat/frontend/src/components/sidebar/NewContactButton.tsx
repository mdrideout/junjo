import useCreateAndUpsertContact from '../../api/contact/hooks/create-upsert-contact-hook'
import { GenderEnum } from '../../api/contact/schemas'

export interface NewContactButtonProps {
  gender: GenderEnum
}

export default function NewContactButton(props: NewContactButtonProps) {
  const { gender } = props
  const { isLoading, error, createContact } = useCreateAndUpsertContact()

  async function handleOnClick(gender: GenderEnum) {
    // Create and upsert the contact
    await createContact(gender)
  }

  switch (gender) {
    case GenderEnum.FEMALE: {
      return (
        <button
          disabled={isLoading}
          onClick={() => handleOnClick(gender)}
          className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-pink-300 rounded-md bg-gradient-to-b from-pink-600 to-pink-700 hover:to-pink-800 disabled:opacity-20 text-white leading-none px-3 py-2"
        >
          <div>{error ? 'Error, Try Again' : 'New Girlfriend'}</div>
          <div className={`${isLoading ? 'animate-rotate' : ''}`}>🙋‍♀️</div>
        </button>
      )
    }

    case GenderEnum.MALE: {
      return (
        <button
          disabled={isLoading}
          onClick={() => handleOnClick(gender)}
          className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 disabled:opacity-20 text-white leading-none px-3 py-2"
        >
          <div>{error ? 'Error, Try Again' : 'New Boyfriend'}</div>
          <div className={`${isLoading ? 'animate-rotate' : ''}`}>🙋‍♂️</div>
        </button>
      )
    }

    default:
      return null
  }
}
