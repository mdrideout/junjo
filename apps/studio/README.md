# Junjo UI

Repository for the FE + BE of the telemetry UI application.

## Frontend

- Vite React SPA

## Backend

- Go Echo Server
- JWT auth middleware
- JSON auth database
- sqlc for queries to the sqlite data

## Running The Dev Environment

#### .env requirements

- `/backend` .env
- `/frontend` .env

### Without Docker

```bash
# Start the backend with hot reloading
$ air

# Build / run the backend
$ go run main.go
```

## Authentication

The backend is uses a JWT based authentication guard. The users database is a JSON file of email addresses and passwords. Do not check this file into the github repository.

#### Managing Users

1.  Locate the `backend/user_db/users-db.example.json` file.
2.  Copy and rename the file to `users-db.json`  
    *This should not be checked into the repository, and is included on the .gitignore list.*
3.  Add new user email and hashed password combinations.
4.  Create password hashes using the `backend/auth/services.go` `HashPassword()` function
    1. *An API endpoint for this is available out of the box, but should be auth-guarded for production.*
    2. GET `http://localhost:1323/hash-password`

```bash
# Example password hashing for the users-db.json file
$ curl --location 'http://localhost:1323/hash-password' \
--header 'Content-Type: application/json' \
--data '{
    "password": "password"
}'
```