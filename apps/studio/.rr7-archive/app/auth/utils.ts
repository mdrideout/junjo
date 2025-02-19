import bcrypt from 'bcryptjs'
import path from 'path'
import { redirect } from 'react-router'
import fs from 'fs/promises'
import { UserDatabaseSchema, type User, type UserDatabase } from './user'
import { getSession } from '~/sessions.server'
import { authenticator } from './authenticator'

const saltRounds = 10

/**
 * Require Session
 *
 * (runs on server)
 *
 * A function that can be utilized inside a page's loader function,
 * to ensure that the user is authenticated before proceeding.
 * @param request
 * @returns
 */
export async function requireSession(request: Request) {
  // Check for a user session
  const session = await getSession(request.headers.get('Cookie'))
  if (!session.has('userId')) {
    throw redirect('/sign-in')
  }

  return
}

/**
 * Is Authenticated
 */
export async function isAuthenticated(request: Request): Promise<boolean> {
  const session = await getSession(request.headers.get('Cookie'))
  if (!session.has('userId')) {
    return false
  }

  return true
}

/**
 * Server Has Users
 *
 * Attempts to read the user's JSON file (database) to determine if any users exist.
 * @returns {boolean} Whether or not the server has any users.
 */
export async function serverHasUsers(request: Request): Promise<boolean> {
  try {
    await loadUserDatabase(request)
    return true
  } catch (error) {
    console.error('Error reading users database:', error)
    return false
  }
}

/**
 * Read And Validate Users DB
 *
 * Attempts to read the user's JSON file (database) to determine if any users exist.
 * @returns {boolean} Whether or not the server has any users.
 */
export async function loadUserDatabase(request: Request): Promise<UserDatabase> {
  const projectRoot = process.cwd()
  const filePath = path.join(projectRoot, 'app', 'auth', 'db', 'users-db.json')
  const data = await fs.readFile(filePath, 'utf-8')
  const users = JSON.parse(data)

  // Validate the users database
  const database = UserDatabaseSchema.safeParse(users)
  if (!database.success) {
    throw new Error('Invalid users database.')
  }

  return database.data
}

/**
 * Hash Password
 *
 * Hashes a password using bcrypt.
 * @param {string} password
 * @returns {Promise<string>} The hashed password
 */
export async function hashPassword(password: string): Promise<string> {
  const hashedPassword = await bcrypt.hash(password, 10)
  return hashedPassword
}

/**
 * Compare Password
 *
 * Compares a password to a hashed password.
 * @param {string} password
 * @param {string} hashedPassword
 * @returns {Promise<boolean>} Whether or not the password matches the hash.
 */
export async function comparePassword(password: string, hashedPassword: string): Promise<boolean> {
  const match = await bcrypt.compare(password, hashedPassword)
  return match
}

/**
 * Authenticate Email / Pass Credentials
 *
 * Authenticates a user by email and password against the users database.
 * @param {string} email
 * @param {string} password
 * @returns {Promise<User>} The authenticated user or null.
 * @throws {Error} If the user is not found or the password is incorrect.
 */
export async function authenticateEmailPassword(
  email: string,
  password: string,
  request: Request
): Promise<User | null> {
  const users = await loadUserDatabase(request)
  const user = users.find((u) => u.email === email)

  if (!user) {
    throw new Error('Invalid email / password combination.')
  }

  const match = await comparePassword(password, user.password)
  if (!match) {
    throw new Error('Invalid email / password combination.')
  }

  return user
}
