# ADR-012: Studio authentication

## Status

Accepted on 2026-10-03, together with
[ADR-011](011-rust-backend-and-single-origin-studio.md).

Its decisions take effect at the cutover of the
[Studio backend Rust migration plan](../../../../docs/roadmaps/STUDIO_BACKEND_RUST_MIGRATION.md).
The CLI browser sign-in follows in that plan's last work package.

## Date

2026-10-03

## Context

Studio has no authentication ADR. Its behavior is spread across code and three
other decisions: Studio ADR-009 for ingestion API-key validation, and Studio
ADR-010 and root ADR 0013 for developer access tokens.

Browser sessions today are a stateless cookie that is signed with one secret
and encrypted with a second. Revocation compares a value in the cookie with the
user's `updated_at` timestamp, so sign-out ends every session for that user
and needs a one-second adjustment to work around whole-second timestamps.

The CLI reads a developer access token from an environment variable. A person
creates that token in the UI and copies it by hand.

Three needs shape this decision:

- avoid building authentication mechanics that a maintained library provides;
- keep the CLI working as it does while giving people a browser sign-in; and
- leave room for a Studio-hosted MCP endpoint without building it now.

## Decision

### Two credential families

| Who | Credential | Authorizes |
| --- | --- | --- |
| A person in a browser | Server-side session | The Studio UI and its API |
| CLI, SDK, automation, and later MCP | Scoped developer access token | Evaluation control and evidence queries |
| An instrumented application | Ingestion API key | OTLP ingestion only |
| Ingestion and backend | Internal workload token | Internal gRPC only |

Sessions are for browsers. Everything else uses a scoped, database-backed
bearer token. Ingestion API keys never authorize the API, and developer access
tokens never authorize ingestion.

### Browser sessions are server-side

`tower-sessions` owns session identifiers, cookie attributes, and expiry. The
session is stored in `junjo.db` through a small store adapter owned by Studio.

- The cookie is host-only, `HttpOnly`, `SameSite=Strict`, and `Secure` in
  production. It carries an opaque identifier and no user data.
- Sign-in rotates the session identifier and binds the user.
- Sign-out ends that session only.
- Sessions last 30 days and activity renews them. The renewal is written at
  most once per day per session, so an authenticated read does not become a
  database write.
- A deleted or inactive user's sessions stop working on the next request.

Both cookie secrets are removed.

### Passwords use bcrypt

Passwords are hashed with bcrypt at cost 12 and must be 8 to 72 bytes, which is
bcrypt's real input limit. Email addresses are validated and lowercased.

Argon2id is not selected. Its recommended parameters use about 19 MiB per hash,
which makes concurrent sign-in attempts a memory risk on a small host.

### Developer access tokens are the single automation credential

Developer access tokens keep their format, scopes, optional expiry, and
recoverable storage as Studio ADR-010 and root ADR 0013 decided. A bearer
credential takes precedence over a session on routes that accept both.

Any future way of obtaining automation access mints a row in the same token
table. This ADR adds one such way.

### The CLI signs in through the browser

`junjo auth login` follows the steps, names, and outcome codes of the OAuth
device authorization grant (RFC 8628), carried in Studio's own JSON and error
conventions.

1. The CLI asks Studio to start a sign-in and receives a short user code and a
   long device code.
2. The CLI shows the code, opens the Studio approval page, and polls.
3. A person signed in to Studio confirms the code and the requested scopes,
   then approves or denies.
4. Approval mints an ordinary developer access token bound to that person.
   The next poll returns it once.

- Pending sign-ins are short-lived and single-use. Approval requires an
  authenticated browser session.
- The CLI stores the token in a private file in the user's configuration
  directory, keyed by Studio origin.
- The environment variable keeps precedence over the stored credential, so
  automation and coding agents behave exactly as before.
- A token can revoke itself, which is what `junjo auth logout` uses.
- The CLI still never accepts a Studio password.

### Ingestion keys and the internal token are unchanged

Studio ADR-009 continues to govern ingestion API-key validation. The internal
workload token is compared in constant time.

### Deferred

- **OAuth 2.1 for a Studio-hosted MCP endpoint.** The MCP specification makes
  authorization optional and directs stdio servers to read credentials from
  the environment, so a local MCP adapter needs nothing new. A hosted endpoint
  needs OAuth 2.1 authorization-server endpoints. That work is its own roadmap
  and will mint rows in the same token table.
- **Hashing tokens at rest.** This would reverse the recoverable-credential
  choice in Studio ADR-010.
- **Sign-in throttling and single sign-on.**

## Alternatives considered

### Keep the stateless encrypted cookie

It needs one or two secrets, hand-written expiry and revocation, and a revision
counter on the user. Sign-out would keep ending every session for the user.

### A hand-written session table

Smaller than a library but still Studio's own session mechanics. The library
provides identifier generation, rotation, cookie handling, and expiry policy.

### `axum-login` on top of `tower-sessions`

Not selected. It trails the session library by a release, and what it adds is
small: binding the user at sign-in, loading the user per request, and clearing
the session at sign-out.

### Renew the session on every request

Rejected. The session library extends expiry only when it saves, so this would
turn every authenticated read into a database write.

### A loopback redirect flow for the CLI

Authorization code with PKCE needs a browser on the same machine and a local
listener. The device grant also works over SSH, in containers, and for coding
agents, and it is the pattern `gh auth login` uses.

### Operating-system keychain storage

Deferred. It would add an SDK dependency and behaves differently on headless
hosts.

### Build the OAuth 2.1 authorization server now

Deferred. No maintained Rust server library exists for it, and nothing needs it
until a hosted MCP endpoint exists.

## Consequences

### Positive

- Session mechanics are owned by a maintained library.
- Two required secrets disappear from every deployment.
- Sign-out ends one session, and the revision workaround is removed.
- People can sign the CLI in without copying a token by hand.
- Later OAuth work has one token store to build on.

### Negative

- Sessions are rows in `junjo.db`, with an occasional renewal write.
- Every user signs in again at cutover.
- Studio owns the store adapter and the device sign-in endpoints.
- The device grant can be abused by tricking a signed-in person into approving
  someone else's code. The approval page must show the code and the requested
  scopes clearly.

## Amendments required

- [Root ADR 0013](../../../../docs/adr/0013-application-executed-studio-evaluations.md):
  the CLI sign-in and the stored credential. Made 2026-10-04.
- [Studio ADR-010](010-evaluation-control-persistence-and-api.md): the wording
  that describes the browser session as encrypted. Made 2026-10-03.

## Related

- [ADR-011: Rust backend and single-origin Studio](011-rust-backend-and-single-origin-studio.md)
- [Studio ADR-009: Bounded ingestion API-key validation](009-bounded-ingestion-api-key-validation.md)
- [Studio ADR-010: Evaluation control persistence and API](010-evaluation-control-persistence-and-api.md)
- [Studio backend Rust migration plan](../../../../docs/roadmaps/STUDIO_BACKEND_RUST_MIGRATION.md)
