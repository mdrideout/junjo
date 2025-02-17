import { useLoaderData } from 'react-router'
import SignInForm from './sign-in-form'
import { serverHasUsers } from '~/auth/utils'
import type { Route } from './+types/sign-in'
// import { action as passwordHashingAction } from './password-hashing-form'
import { action as signInAction } from './sign-in-form'
import UsersExplanation from '~/auth/users-explanation'

interface SignInLoaderData {
  hasUsers: boolean
}

export default function SignIn() {
  const { hasUsers } = useLoaderData<SignInLoaderData>()

  return (
    <div>
      <h1>Sign In</h1>
      <div className="mb-2">{hasUsers ? <SignInForm /> : <p>Create some users to enable sign in.</p>}</div>
      <UsersExplanation />
    </div>
  )
}

export async function loader({ request }: Route.LoaderArgs): Promise<SignInLoaderData> {
  const hasUsers: boolean = await serverHasUsers(request)
  return { hasUsers }
}

// Unified action function for handling form submissions
export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData()
  const actionType = formData.get('actionType')

  switch (actionType) {
    case 'signIn':
      return signInAction
    default:
      throw new Error('Unknown action type')
  }
}
