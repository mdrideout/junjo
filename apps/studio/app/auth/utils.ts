import bcrypt from 'bcryptjs'
import path from 'path'
import { redirect } from 'react-router'
import fs from 'fs/promises'
import { UserDatabaseSchema, type UserDatabase } from './user'

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
  console.log('Server session check for user running...')
  console.warn('TODO: Implement authentication.')

  const user = null

  if (!user) {
    throw redirect('/sign-in')
  }
  return user
}

/**
 * Is Authenticated
 */
export function isAuthenticated(request: Request): boolean {
  console.log('Client session check for user running...')

  const user = null

  return !!user
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
