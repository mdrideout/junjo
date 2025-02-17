import { Form, useActionData } from 'react-router'

interface SignInFormResponse {
  error: string
}

export default function SignInForm() {
  const data = useActionData<SignInFormResponse>()

  // Form Data
  let error = data?.error

  return (
    <>
      <Form method="post">
        <div className="flex flex-col gap-y-2 w-xs">
          <input type="hidden" name="actionType" value="signIn" />
          <input
            type="email"
            name="email"
            placeholder="Email address"
            required
            className="bg-slate-300 text-black py-1 px-2 rounded-sm"
          />
          <input
            type="password"
            name="password"
            placeholder="Password"
            autoComplete="current-password"
            required
            className="bg-slate-300 text-black py-1 px-2 rounded-sm"
          />
          <button className="py-1 px-2 bg-gray-200 hover:bg-gray-300 cursor-pointer rounded-md font-bold">
            Sign In
          </button>
          {error ? <div className="text-red-700 text-center text-sm">{error}</div> : null}
        </div>
      </Form>
    </>
  )
}

// /**
//  * Sign in form loader
//  *
//  * Redirects to the dashboard if the user is already signed in.
//  * @param param0
//  * @returns
//  */
// export async function loader({ request }: Route.LoaderArgs) {
//   const session = await getSession(request.headers.get('Cookie'))

//   if (session.has('userId')) {
//     return redirect('/dashboard')
//   }

//   return data(
//     { error: session.get('error') },
//     {
//       headers: {
//         'Set-Cookie': await commitSession(session),
//       },
//     }
//   )
// }
