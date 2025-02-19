import { Authenticator } from 'remix-auth'
import { FormStrategy } from 'remix-auth-form'
import type { User } from './user'
import { authenticateEmailPassword } from './utils'

export let authenticator = new Authenticator<User>()

authenticator.use(
  new FormStrategy(async ({ form, request }) => {
    // Use `form` to access and input values from the form.
    // Use `request` to access more data
    let email = form.get('email')
    let password = form.get('password')

    // Validate the inputs
    if (!email || !password) {
      throw new Error('Email and password are required')
    }

    if (typeof email !== 'string') {
      throw new Error('Invalid email address')
    }

    if (typeof password !== 'string' || password.length < 1) {
      throw new Error('Invalid password')
    }

    // Authenticate the email / password
    const user = await authenticateEmailPassword(email, password, request)
    if (!user) {
      throw new Error('Invalid email / password combination')
    }

    // And return the user as the Authenticator expects it
    return user
  }),
  'email-pass'
)
