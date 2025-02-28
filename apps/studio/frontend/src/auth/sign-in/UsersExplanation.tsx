/**
 * Users Explanation
 *
 * Explans how users work in this auth system.
 * @returns
 */
export default function UsersExplanation() {
  return (
    <div className="bg-zinc-600 p-4 rounded-lg max-w-xl">
      <h6>Managing Users</h6>
      <ol className="mb-4">
        <li>
          Locate the <b>backend/user_db/users-db.example.json</b> file in this project's backend.
        </li>
        <li>
          Copy and rename the file to <b>users-db.json</b>
          <br />
          <i>This should not be checked into the repository, and is included on the .gitignore list.</i>
        </li>
        <li>Add new user email and hashed password combinations.</li>
        <li>
          Create password hashes using the the backend's hash password endpoint: http://localhost:1323/hash-password
          <br />
          <i>See the README.md for more information.</i>
          <br />
          <i>Authentication guard this endpoint for production.</i>
        </li>
      </ol>
    </div>
  )
}

// Loader Function
