interface NewContactButtonProps {
  loading: boolean
  onCreate: (sex: 'male' | 'female') => Promise<void>
}

export default function NewContactButton({ loading, onCreate }: NewContactButtonProps) {
  const button = 'flex items-center gap-x-2 justify-center font-bold w-full cursor-pointer border rounded-2xl disabled:opacity-60 text-white leading-none px-3 py-5'
  return (
    <div className="flex flex-col gap-y-2">
      <button
        disabled={loading}
        onClick={() => void onCreate('male')}
        className={`${button} border-blue-300 bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800`}
      >
        <div>New Male</div><div className={loading ? 'animate-rotate' : ''}>🙋‍♂️</div>
      </button>
      <button
        disabled={loading}
        onClick={() => void onCreate('female')}
        className={`${button} border-pink-300 bg-gradient-to-b from-pink-600 to-pink-700 hover:to-pink-800`}
      >
        <div>New Female</div><div className={loading ? 'animate-rotate' : ''}>🙋‍♀️</div>
      </button>
    </div>
  )
}
