---
name: junjo-local-development
description: Prepare, reset, provision, or validate the repository-local Junjo AI Studio stack and its SDK example environments. Use for local development and E2E workflows, not production deployments.
---

# Junjo Local Development

## Owners

- Read `apps/studio/TESTING.md` for the greenfield reset, local identity,
  credential provisioning, and validation workflow.
- Read the selected example's README and `.env.example` for its runtime and
  configuration contract.
- Use `tooling/scripts/provision_local_studio.py` to prepare persistent local
  Studio credentials and ignored example environments.

## Required boundaries

- Create the local owner and credentials only through Studio's public setup,
  session, and management APIs.
- Never edit SQLite, add migration or startup seeds, commit generated
  credentials, or copy local `.env` files into deployment artifacts.
- Use persistent provisioned credentials for local human or coding-agent
  iteration. Keep automated validators isolated with disposable credentials
  that they create and remove themselves.
- Treat `apps/studio/TESTING.md` and the example-owned files as sources of
  truth. Do not reproduce their endpoint, credential, or environment details
  in new agent guidance.

## Workflow

1. Identify whether the task needs an ordinary restart or an explicitly
   authorized greenfield reset.
2. Follow the Studio testing runbook to configure and start the development
   stack.
3. Run the local provisioner before starting examples or evaluation commands.
4. Follow the selected example's own run and validation instructions.
5. Keep production deployment work in its owning deployment workflow; the
   local provisioner must never be used against production or a remote Studio.
