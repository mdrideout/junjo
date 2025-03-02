import useCreateAndUpsertContact from '../../api/contact/hook'
import { GenderEnum } from '../../api/contact/schemas'

export interface NewContactButtonProps {
  gender: GenderEnum
}

export default function NewContactButton(props: NewContactButtonProps) {
  const { gender } = props
  const { isLoading, error, createContact } = useCreateAndUpsertContact()

  switch (gender) {
    case GenderEnum.FEMALE: {
      return (
        <button
          onClick={() => createContact(gender)}
          className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-pink-300 rounded-md bg-gradient-to-b from-pink-600 to-pink-700 hover:to-pink-800 text-white leading-none px-3 py-2"
        >
          <div>{error ? 'Error, Try Again' : 'New Girlfriend'}</div>
          <div className={`${isLoading ? 'animate-rotate' : ''}`}>🙋‍♀️</div>
        </button>
      )
    }

    case GenderEnum.MALE: {
      return (
        <button
          onClick={() => createContact(gender)}
          className="flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 text-white leading-none px-3 py-2"
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
