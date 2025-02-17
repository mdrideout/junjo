import { Outlet } from "react-router";
import { requireSession } from "~/auth/require-session";
import type { Route } from "./+types/dashboard";

export default function Dashboard() {
  return (
    <div>
      <h1>Dashboard</h1>
      <Outlet />
    </div>
  );
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
  await requireSession(request);
  return null;
}
