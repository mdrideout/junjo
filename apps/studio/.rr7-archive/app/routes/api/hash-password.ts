import { hashPassword } from '~/auth/utils'
import type { Route } from './+types/hash-password'

export interface HashPasswordResponse {
  hashedPassword: string
  error?: string
}

export async function action({ request }: Route.ActionArgs): Promise<HashPasswordResponse> {
  console.log('Hash password API route running...')

  let formData = await request.formData()
  let passwordFieldData = formData.get('password')
  const passwordString = passwordFieldData?.toString()

  if (!passwordString) {
    return {
      hashedPassword: '',
      error: 'Error parsing password form data.',
    }
  }

  try {
    const hashedPassword = await hashPassword(passwordString)
    console.log('Returning hashed password', hashedPassword)
    return { hashedPassword }
  } catch (error) {
    return {
      hashedPassword: '',
      error: 'Error hashing password',
    }
  }
}
