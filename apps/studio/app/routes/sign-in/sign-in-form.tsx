import { data, Form, redirect } from 'react-router'
import { authenticator } from '~/auth/authenticator'
import type { Route } from './+types/sign-in'

export default function SignInForm() {
  return (
    <Form method="post">
      <input type="hidden" name="actionType" value="signIn" />
      <input type="email" name="email" required className="bg-slate-300 text-black m-1 px-1 rounded-sm" />
      <input
        type="password"
        name="password"
        autoComplete="current-password"
        required
        className="bg-slate-300 text-black m-1 px-1 rounded-sm"
      />
      <button>Sign In</button>
    </Form>
  )
}

// Handle the form action
export async function action({ request }: Route.ActionArgs) {
  // we call the method with the name of the strategy we want to use and the
  // request object
  let user = await authenticator.authenticate('form', request)

  let session = await sessionStorage.getSession(request.headers.get('cookie'))
  session.set('user', user)

  throw redirect('/', {
    headers: { 'Set-Cookie': await sessionStorage.commitSession(session) },
  })
}

// Finally, we need to export a loader function to check if the user is already
// authenticated and redirect them to the dashboard
export async function loader({ request }: Route.LoaderArgs) {
  let session = await sessionStorage.getSession(request.headers.get('cookie'))
  let user = session.get('user')
  if (user) throw redirect('/')
  return data(null)
}
