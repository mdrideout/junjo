---
title: Platform boundaries
description: Ownership and integration boundaries across the Junjo platform.
---

Junjo is a platform with independently built components. The monorepo provides
one integration boundary; it does not create one shared runtime or dependency
graph.

## Python SDK

The Python SDK provides graph, workflow, state, store, lifecycle, hook, and
OpenTelemetry primitives to Python applications. It does not depend on Junjo AI
Studio runtime code or a particular model provider.

- [Python SDK documentation](https://python-api.junjo.ai/)
- [SDK source](https://github.com/mdrideout/junjo/tree/master/sdks/python)
- [Examples](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples)

## Junjo AI Studio

Junjo AI Studio is the optional evidence and control plane for Junjo execution
telemetry. Its ingestion, backend, and frontend services consume the explicit
telemetry contract rather than Python SDK internals.

- [Studio source](https://github.com/mdrideout/junjo/tree/master/apps/studio)
- [Minimal deployment](https://github.com/mdrideout/junjo-ai-studio-minimal-build)
- [VM and Caddy deployment](https://github.com/mdrideout/junjo-ai-studio-deployment-example)

## Telemetry contract

The language-independent telemetry schemas and conformance fixtures live in
[`contracts/telemetry`](https://github.com/mdrideout/junjo/tree/master/contracts/telemetry).
SDK emitters and Studio consumers evolve together against that contract while
remaining separate implementations.

## Website

This website owns the platform narrative, introductory guides, and navigation.
It links to component-owned reference documentation instead of maintaining a
second copy of the Python API.
