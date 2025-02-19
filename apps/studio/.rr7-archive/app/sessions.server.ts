import { createCookieSessionStorage } from 'react-router'

type SessionData = {
  userId: string
}

type SessionFlashData = {
  error: string
}

const { getSession, commitSession, destroySession } = createCookieSessionStorage<SessionData, SessionFlashData>({
  cookie: {
    name: '__session',

    // Optional
    maxAge: 60 * 60 * 24 * 7, // 7 day
    httpOnly: true,
    secure: true,
    sameSite: 'strict',

    // Sign the cookie with a secret
    // Add new keys to the front of the array to rotate secrets (allows old secrets to validate old cookies)
    // Reset the array to invalidate all existing cookies
    secrets: ['wyw-RiimBDCp'], // https://reactrouter.com/explanation/sessions-and-cookies#signing-cookies
  },
})

export { getSession, commitSession, destroySession }
