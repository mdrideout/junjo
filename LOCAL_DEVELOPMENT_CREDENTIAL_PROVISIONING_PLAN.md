# Local Development Credential Provisioning Plan

- Status: Implemented and E2E validated
- Date: 2026-08-22
- Owners: Junjo platform tooling, Junjo AI Studio, and Python SDK examples
- Scope: Explicit local Studio provisioning, example environment configuration,
  agent-facing guidance, and end-to-end validation

## Document purpose and authority

This document is the persistent implementation plan for accelerating fresh
local Junjo development environments. It defines how a developer or coding
agent will create the standard local user, provision reusable Studio
credentials through the real product APIs, and configure repository examples
without manually copying secrets.

This plan does not replace implementation-owned contracts or human runbooks:

- Studio authentication behavior remains owned by backend code and tests.
- `apps/studio/TESTING.md` owns the human greenfield reset, provisioning, and
  validation procedure.
- Each example's `.env.example` owns the variables and explanatory comments for
  that example.
- Repo-local skills route coding agents to those owners without duplicating
  implementation details or secrets.

There is no dedicated Studio authentication ADR today. If implementation
requires a new persistent authentication decision beyond the boundaries in
this plan, that decision must be reviewed before expanding the work.

## Goal

Provide one explicit, repeatable command that turns a running, repository-local
Studio development stack into a ready-to-use environment for application
telemetry and SDK/CLI evaluation work.

After the command completes:

- the documented local user exists through the public first-user setup flow;
- one reusable Application Telemetry API Key exists;
- one reusable Developer Access Token exists with the complete evaluation and
  evidence authority needed by local coding agents;
- supported example `.env` files contain the generated credentials and local
  Studio endpoints;
- unrelated example configuration, including model-provider credentials, is
  preserved; and
- rerunning the command does not create duplicate local credentials.

## Current repository facts

The implementation will build on existing behavior rather than introduce a
parallel credential system:

- Studio exposes its non-sensitive runtime environment through
  `GET /api/config`.
- The local development backend is `http://localhost:26154`.
- The public first-user setup endpoint is `POST /users/create-first-user`.
- Normal session authentication uses `POST /sign-in`.
- Authenticated Application Telemetry API Key management uses `/api_keys` and
  generates canonical `jtel_` credentials.
- Authenticated Developer Access Token management uses
  `/api/v1/evaluation-tokens` and generates canonical `jcli_` credentials.
- Credential list responses currently expose the recoverable canonical values,
  allowing an idempotent local provisioner to reuse a named credential.
- The live E2E validators already create the local owner through the setup API
  and create disposable credentials through the normal management APIs.
- Example `.env` files are gitignored. Their `.env.example` templates already
  distinguish application telemetry from developer control/query access.
- Studio currently recognizes `development` and `production`, but the backend
  setting is typed as an unrestricted string and treats every non-production
  value as development behavior.

## Product and security decisions

### Provisioning is explicit, never automatic

The local credentials will be created only when a developer or coding agent
runs the provisioning command. They will not be created by:

- application startup;
- Docker Compose startup;
- migrations;
- database initialization;
- container image builds; or
- direct SQLite reads or writes.

The command will use the same setup, sign-in, and credential-management APIs
used by the Studio UI.

### Local development uses real credentials

The provisioner will create normal `jtel_` and `jcli_` credentials. Local E2E
must exercise the same authentication paths as ordinary use.

No `test_`, `jtel_test_`, `jcli_test_`, or other environment-specific secret
prefix will be introduced. Credential prefixes identify authority, not the
deployment in which a credential was created.

### Environment isolation comes from the runtime and credential store

Production isolation will not depend on recognizing a string inside a secret.
It will come from:

- a provisioner that accepts only the repository-local loopback backend;
- an exact `development` response from Studio's runtime configuration;
- separate development and production credential databases;
- ignored local environment files; and
- exclusion of the repository-local provisioner from published Studio
  deployment distributions.

A credential created in the local database is not valid in a production
credential database. Copying a development data directory into production is
outside the supported deployment flow.

### Development remains the live E2E mode

No third Studio `test` deployment mode will be introduced. Unit and integration
tests continue to use isolated test settings and databases. Live E2E work uses
the real development stack.

### Persistent development credentials and disposable test credentials differ

The provisioned local credentials are shared conveniences for human and coding
agent iteration. Automated validators that prove isolation, creation,
revocation, or cleanup will continue to create and delete their own disposable
credentials.

The persistent credentials must not become hidden prerequisites for hermetic
test suites.

## Intended developer experience

The complete greenfield flow will be:

```text
Configure Studio .env
        |
Start the local development stack
        |
Run the explicit local provisioner
        |
        +-- create or authenticate admin@test.com through Studio HTTP APIs
        +-- create or reuse one jtel_ telemetry key
        +-- create or reuse one jcli_ developer token
        +-- update ignored example .env files
        |
Run examples, Junjo CLI commands, and coding-agent evaluation loops
        |
Inspect telemetry, datasets, evaluation runs, and evidence in Studio
```

The target command will be a repository-root tool with a direct, memorable
invocation:

```bash
python3 tooling/scripts/provision_local_studio.py
```

The provisioner will use the existing documented local owner:

- Email: `admin@test.com`
- Password: `JunjoAIStudioLocalTestPass1!`

Those values are local testing defaults, not production credentials and not
backend startup configuration.

## Credential definitions

### Application Telemetry API Key

- Studio display name: `Local Development Application Telemetry`
- Canonical format: existing `jtel_` generator
- Purpose: OTLP telemetry from repository examples into Studio ingestion
- Example environment variable: `JUNJO_AI_STUDIO_API_KEY`
- Lifetime: retained until the local Studio data is wiped or the key is
  explicitly deleted

### Developer Access Token

- Studio display name: `Local Development Developer Access`
- Canonical format: existing `jcli_` generator
- Purpose: Junjo SDK and CLI access to datasets, evaluation runs, and evidence
- Scopes:
  - `evaluation:read`
  - `evaluation:write`
  - `evidence:read`
- Expiration: none
- Example environment variable: `JUNJO_AI_STUDIO_CLI_TOKEN`
- Lifetime: retained until the local Studio data is wiped or the token is
  explicitly deleted

One credential of each type will be shared across the supported local examples.
OpenTelemetry service identity already distinguishes the applications and
their traces, so per-example credentials are not required for local iteration.

## Implementation plan

### 1. Make the Studio environment value fail closed

Change the backend `JUNJO_ENV` setting from an unrestricted string to a closed
`development | production` value.

Required behavior:

- `development` retains the current local URLs, non-HTTPS cookies, and local
  CORS behavior.
- `production` retains the current production validation and secure-cookie
  behavior.
- typos and unsupported values fail application settings validation instead of
  silently entering development behavior.
- `/api/config` continues returning the active canonical environment value.

This is a settings hardening change, not a new deployment mode or authentication
architecture.

### 2. Add the explicit repository-local provisioner

Add `tooling/scripts/provision_local_studio.py` as a standard-library Python
script. It will orchestrate existing public APIs and will not import Studio
runtime or database code.

Before any mutation, the script must:

1. Resolve the configured backend URL.
2. Require HTTP and a loopback host.
3. Call `GET /api/config`.
4. Require the returned environment to equal `development` exactly.
5. Confirm the normal Studio health boundary is available.

The command will have no flag that bypasses the loopback or environment guard.
Remote and production provisioning is deliberately unsupported.

### 3. Use the normal setup and session-authentication flow

The provisioner will:

1. Call the existing setup-status endpoint.
2. Create `admin@test.com` through `POST /users/create-first-user` only when the
   database has no users.
3. Sign in through `POST /sign-in` using an isolated cookie jar.
4. Confirm the authenticated identity through the existing authentication
   endpoint before creating credentials.

If users already exist and the documented local owner cannot sign in, the
command will stop with a credential-free explanation. It will not reset the
password, alter the database, or create another privileged path.

### 4. Create or reuse named local credentials

For each credential type, the provisioner will list credentials through the
authenticated management API and match the exact local-development display
name.

- No match: create the credential through the normal POST endpoint.
- One match: reuse its canonical credential value.
- Multiple exact matches: stop and report the duplicate names rather than
  choosing an arbitrary credential.

This makes a second run idempotent and avoids accumulating credentials after
ordinary development restarts.

The provisioner will not parse credential contents beyond requiring a
non-empty value from the typed API response. Authentication validity remains
owned by Studio's normal credential lookup, not by client-side regexes or
prefix checks.

### 5. Configure supported example environments safely

The first supported targets are:

- `sdks/python/examples/ai_chat/.env`
- `sdks/python/examples/base_openai_agents/.env`
- `sdks/python/examples/base/.env`

For a missing `.env`, the provisioner will start from that example's existing
`.env.example`. For an existing `.env`, it will change only Studio-owned local
connection and credential variables.

Variables will be set only where the example consumes them:

- `JUNJO_AI_STUDIO_API_KEY`
- `JUNJO_AI_STUDIO_CLI_TOKEN`
- `JUNJO_AI_STUDIO_OTLP_ENDPOINT`
- `JUNJO_AI_STUDIO_OTLP_INSECURE`
- `JUNJO_AI_STUDIO_BACKEND_BASE_URL`
- `JUNJO_AI_STUDIO_FRONTEND_BASE_URL`

The exact variable set remains owned by each example's `.env.example`; the
provisioner must not add irrelevant settings merely to make all files look the
same.

Environment-file handling must:

- preserve comments, ordering, unrelated values, and provider secrets;
- activate an existing commented credential placeholder rather than leave
  confusing duplicate assignments;
- avoid duplicate active assignments;
- write through an atomic replacement;
- set the resulting file mode to `0600`;
- never modify `.env.example`; and
- never print canonical credentials.

The generated environment values are:

- backend: `http://localhost:26154`
- frontend: `http://localhost:26151`
- OTLP/gRPC: `localhost:26155`
- OTLP insecure transport: `true`

### 6. Keep secret values out of repository artifacts

The implementation will verify that generated files remain ignored and will
not add credential values to:

- source-controlled templates;
- logs;
- exception messages;
- command arguments;
- test snapshots;
- build artifacts; or
- documentation.

Console output may include credential display names, record IDs, target files,
and redacted previews. It must never include the full `jtel_` or `jcli_` value.

### 7. Add concise documentation and coding-agent routing

Update `apps/studio/TESTING.md` with the canonical human flow:

1. configure Studio;
2. start the development stack;
3. run the local provisioner;
4. run supported examples and CLI checks;
5. perform a greenfield reset when required.

The runbook will distinguish persistent local credentials from disposable E2E
validator credentials and retain the prohibition on live database access.

Add a small repo-local `junjo-local-development` skill that is triggered for
fresh local stack setup, example configuration, and local end-to-end testing.
The skill will:

- link to `apps/studio/TESTING.md` as the procedural owner;
- link to the relevant example README and `.env.example` as configuration
  owners;
- instruct the coding agent to use the provisioner;
- prohibit direct database edits, startup seeding, and committed secrets; and
- preserve the distinction between persistent development and disposable test
  credentials.

The skill will not duplicate endpoint lists, credential values, or the
provisioner's implementation.

Update the existing `studio-security-auth` skill only if a routing link is
needed. Do not copy the new runbook into that skill.

## Non-goals

This work will not:

- seed users or credentials in migrations or startup code;
- add a development-only backend credential-creation endpoint;
- add a `test` Studio runtime mode;
- add environment-specific credential prefixes;
- change API-key or access-token authentication semantics;
- change ingestion caching, authorization, or transport behavior;
- automatically start or wipe the Studio stack;
- reset an existing user's password;
- configure third-party model-provider secrets;
- make local credentials a prerequisite for isolated automated tests;
- publish the local provisioner in Studio deployment distributions; or
- modify production/cloud deployment setup.

## Test and validation plan

### Provisioner tests

Add focused tests for the repository-local script covering:

- rejection of a non-loopback backend URL before any mutation;
- rejection when `/api/config` reports `production`;
- rejection of an unknown environment value;
- first-user creation on an empty Studio response;
- normal sign-in when the local user already exists;
- failure without password resets when existing authentication fails;
- creation of one API key and one access token;
- exact access-token scopes and no expiration;
- reuse of existing named credentials;
- duplicate-name failure;
- a second invocation producing no additional credential records;
- creation of a missing `.env` from its template;
- preservation of unrelated and secret example settings;
- replacement of commented placeholders without duplicate assignments;
- atomic `0600` environment-file output; and
- redacted stdout and exceptions.

### Studio settings and authentication tests

Validate:

- `development` settings still load;
- `production` settings still enforce all existing requirements;
- unsupported `JUNJO_ENV` values fail settings construction;
- `/api/config` returns only canonical values;
- a provisioned `jtel_` key authenticates through the normal backend-to-ingestion
  validation path; and
- a provisioned `jcli_` token authorizes the expected evaluation and evidence
  routes through their existing scope checks.

No extra cross-credential or prefix-validation matrix will be added. Existing
route ownership and authentication tests remain sufficient for distinguishing
the two credential systems.

### Greenfield live E2E

From a stopped local stack:

1. Remove the disposable development data directory.
2. Recreate the empty shared data root before either container starts.
3. Start Studio in development mode.
4. Run the provisioner.
5. Run the provisioner again and verify no duplicate records.
6. Sign into Studio using the documented local user.
7. Confirm one named credential appears on API Keys and one on Access Tokens.
8. Start AI Chat with its generated environment and verify application
   telemetry reaches Studio.
9. Run the AI Chat evaluation capability, target, and evaluator discovery
   commands using the generated access token.
10. Run the provider-free OpenAI Agents example and its evaluation discovery
   commands.
11. Open the resulting traces and native Junjo execution views in Chrome.
12. Run the installed-SDK evaluation E2E validator to prove disposable
    credential behavior still works independently.
13. Stop the stack cleanly and inspect logs for authentication, ingestion, or
    shutdown errors.

### Production-safety validation

Prove that:

- the provisioner refuses a non-loopback URL;
- the provisioner refuses a loopback server reporting `production`;
- no provisioner file is included in generated minimal or VM/Caddy deployment
  distributions;
- no example `.env` is tracked or exported; and
- repository secret/invariant validation remains green.

### Owning validation suites

Run every suite affected by implementation:

- focused provisioning-tool tests;
- Studio backend settings and authentication tests;
- Studio's complete `apps/studio/run-all-tests.sh` suite;
- ingestion tests if the live credential proof or implementation touches its
  code (no ingestion code change is currently planned);
- Python SDK example smoke and evaluation tests;
- repository invariant validation;
- Studio deployment distribution validation; and
- the live Compose and Chrome E2E flow above.

## Delivery order

Implement in the following order so each increment is independently
reviewable:

1. Close the `JUNJO_ENV` value and validate settings.
2. Add the guarded API-driven provisioner and focused tests.
3. Add safe example `.env` synchronization and tests.
4. Update the human runbook and add the agent-routing skill.
5. Run focused component validation.
6. Run the complete Studio, SDK example, repository, and distribution suites.
7. Perform the greenfield live E2E proof.
8. Review the final diff for secret leakage, duplicated documentation, and
   unplanned authentication changes.

## Completion criteria

This plan is complete only when all of the following are true:

- one explicit command provisions a fresh local development Studio through
  normal HTTP APIs;
- no startup, migration, Compose, or database seeding exists;
- repeated provisioning reuses exactly one named credential of each type;
- supported example `.env` files are ready for local Studio without losing
  unrelated configuration;
- the provisioner cannot target a remote or production Studio;
- `JUNJO_ENV` rejects unsupported values;
- normal `jtel_` ingestion and `jcli_` SDK/CLI access work end to end;
- automated validators remain credential-isolated and cleanup-safe;
- no canonical credential appears in tracked files, logs, snapshots, or build
  outputs;
- the runbook and agent skill point to the correct sources of truth; and
- all owning validation suites and the greenfield Chrome E2E review pass.

## Deferred considerations

The following may be considered only after real use demonstrates a need:

- selecting a subset of examples instead of configuring all supported local
  examples;
- rotating the persistent local credentials without wiping Studio data;
- supporting a non-default local port topology; and
- extracting shared HTTP or environment-file helpers if multiple independent
  tooling commands develop the same behavior.

These are not required for the initial implementation and should not add
abstractions to the critical path.
