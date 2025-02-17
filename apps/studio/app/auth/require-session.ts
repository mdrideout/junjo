import { redirect } from "react-router";

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
  console.log("Server session check for user running...");
  console.warn("TODO: Implement authentication.");

  const user = null;

  if (!user) {
    throw redirect("/sign-in");
  }
  return user;
}
