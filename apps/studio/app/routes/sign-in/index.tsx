import { redirect, useLoaderData } from 'react-router'
import SignInForm from './sign-in-form'
import { serverHasUsers } from '~/auth/utils'
import type { Route } from './+types/sign-in'
// import { action as passwordHashingAction } from './password-hashing-form'
// import { action as signInAction } from './sign-in-form'
import UsersExplanation from '~/auth/users-explanation'
import { authenticator } from '~/auth/authenticator'
import { getSession, commitSession } from '~/sessions.server'

interface SignInLoaderData {
  hasUsers: boolean
}

export default function SignIn() {
  const { hasUsers } = useLoaderData<SignInLoaderData>()

  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col">
        <h1>SIGN IN</h1>
        <div className="mb-2">
          {hasUsers ? (
            <SignInForm />
          ) : (
            <div>
              <p>Create some users to enable sign in.</p>
              <UsersExplanation />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export async function loader({ request }: Route.LoaderArgs): Promise<SignInLoaderData> {
  const hasUsers: boolean = await serverHasUsers(request)
  return { hasUsers }
}

// Handle the form action
export async function action({ request }: Route.ActionArgs) {
  try {
    // Call the authentication strategy to find the user
    let user = await authenticator.authenticate('email-pass', request)

    // Get the session
    const session = await getSession(request.headers.get('Cookie'))
    session.set('userId', user.email)

    return redirect('/dashboard', {
      headers: { 'Set-Cookie': await commitSession(session) },
    })
  } catch (error) {
    if (error instanceof Error) {
      console.error('Error authenticating user:', error.message)
      return { error: error.message }
    } else {
      console.error('Unknown error authenticating user:', error)
      return { error: 'An unknown error occurred' }
    }
  }
}
