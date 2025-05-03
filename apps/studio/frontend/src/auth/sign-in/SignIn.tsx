import SignInForm from './SignInForm'
import UsersExplanation from './UsersExplanation'

export default function SignIn() {
  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col">
        <h1>SIGN IN</h1>
        <SignInForm />
        <UsersExplanation />
      </div>
    </div>
  )
}
