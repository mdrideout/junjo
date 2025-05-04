import SignInForm from './SignInForm'

export default function SignIn() {
  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col">
        <h1>SIGN IN</h1>
        <SignInForm />
      </div>
    </div>
  )
}
