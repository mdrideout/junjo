.. _api:

API Reference
============================

Core API
--------

.. automodule:: junjo
   :members:
   :undoc-members:
   :show-inheritance:
   :exclude-members: Agent, AgentConfigurationError, AgentError,
      AgentExecutionError, AgentExecutionResult, AgentLimits, AgentRunContext,
      AgentStateSnapshot, ModelDriver, ModelDriverBinding,
      ModelDriverDescriptor, Tool

Agent API
---------

The common definition and binding types are also available from ``junjo``.
Provider-neutral messages, results, and typed errors live in ``junjo.agent``.
Deterministic scripted testing support is intentionally public at
``junjo.agent.testing``.

.. automodule:: junjo.agent.definition
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.model_driver
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.messages
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.result
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.state
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.json
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.errors
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: junjo.agent.testing
   :members:
   :undoc-members:
   :show-inheritance:

Hooks API
---------

.. automodule:: junjo.hooks
   :members:
   :undoc-members:
   :show-inheritance:
   :exclude-members: Hooks

Telemetry API
-------------

.. automodule:: junjo.telemetry.junjo_otel_exporter
   :members:
   :undoc-members:
   :show-inheritance:
