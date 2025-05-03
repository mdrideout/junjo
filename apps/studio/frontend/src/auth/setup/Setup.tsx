import SetupForm from './SetupForm'

export default function Setup() {
  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col w-sm">
        <h1>Welcome</h1>
        <p>Create your first user account.</p>
        <div className={'h-3'} />
        <SetupForm />
      </div>
    </div>
  )
}
