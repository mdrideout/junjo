import PasswordHashingForm from './password-hashing-form'

/**
 * Users Explanation
 *
 * Explans how users work in this auth system.
 * @returns
 */
export default function UsersExplanation() {
  return (
    <div className="bg-gray-100 p-4 rounded-lg">
      <h4>Managing Users</h4>
      <ol className="mb-4">
        <li>
          Locate the <b>users-db.example.json</b> file in the root of this project.
        </li>
        <li>
          Copy and rename the file to <b>users-db.json</b>
          <br />
          <i>This should not be checked into the repository, and is included on the .gitignore list.</i>
        </li>
        <li>Add new user email and hashed password combinations.</li>
        <li>
          Create password hashes using the form below.
          <br />
          <i>This utilizes the same hashing pattern used to validate login attempts.</i>
        </li>
      </ol>

      <PasswordHashingForm />
    </div>
  )
}

// Loader Function
