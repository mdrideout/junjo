import { Outlet } from 'react-router'
import { requireSession } from '~/auth/utils'
import type { Route } from './+types/dashboard'

export default function Dashboard() {
  return (
    <>
      <h1 className="pt-4 px-5.5">Dashboard</h1>
      <Outlet />
    </>
  )
}

/**
 * Dashboard Loader
 *
 * (runs on server)
 *
 * Ensures that the user is authenticated before proceeding.
 *
 * @param param0
 * @returns
 */
export async function loader({ request }: Route.LoaderArgs) {
  await requireSession(request)
  return null
}
