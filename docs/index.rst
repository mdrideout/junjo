.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :hidden:

   getting_started
   tutorial
   core_concepts
   state_management
   concurrency
   subflows
   visualizing_workflows
   eval_driven_dev
   api

.. toctree::
   :maxdepth: 2
   :caption: Junjo Server:
   :hidden:

   junjo_server
   deployment
   opentelemetry

.. toctree::
   :maxdepth: 1
   :caption: External Links
   :hidden:

   Junjo PyPI <https://pypi.org/project/junjo/>
   GitHub - Junjo <https://github.com/mdrideout/junjo>
   GitHub - Junjo Server <https://github.com/mdrideout/junjo-server>


.. toctree::
   :maxdepth: 1
   :caption: Example Apps
   :hidden:

   Base Example <https://github.com/mdrideout/junjo/tree/main/examples/base>
   AI Chat <https://github.com/mdrideout/junjo/tree/main/examples/ai_chat>

Junjo 順序 - Python API Reference
==================================

`Junjo on PyPI <https://pypi.org/project/junjo/>`_

Junjo is a modern Python library for building, executing, testing, and debugging complex, graph-based AI workflows.

Junjo makes it easy to build a graph of possible paths for an AI to take. When the graph executed, the LLM will autonomously traverse the graph, choosing the next node as it goes based on application state and edge conditions.

Whether you're building a simple chatbot, a complex data manipulation pipeline, or a sophisticated workflow with dynamic branching and parallel execution, Junjo provides the tools to define your logic as a clear graph of nodes and edges, and telemetry to make it easy to debug.

.. image:: _static/junjo-screenshot.png
   :alt: A screenshot of a Junjo workflow graph's telemetry on Junjo Server
   :align: center
   :width: 600px

*A screenshot of Junjo's companion open-telemetry ingestion server to make debugging graph workflow state easy.*

Junjo remains decoupled from any specific AI model or framework. Simply wrap your existing business logic in a Junjo node, organize them into a Graph with conditional edges, and then execute the graph. Junjo will handle the rest, including task orchestration, error handling, and logging to any OpenTelemetry destination.

Junjo's optional companion library, `Junjo Server <https://github.com/mdrideout/junjo-server>`_, provides additional features for observing graph execution telemetry, and visually stepping through state changes made by each node. This is particularly useful for debugging complex workflows or understanding how data flows through your application.

With built-in support for fully type-safe (Pydantic) redux-inspired state management, conditional execution, concurrent tasks (asyncio), and native OpenTelemetry support, Junjo empowers you to create robust, observable, and scalable Python workflows. Dive into our documentation to learn how to streamline your task orchestration and gain deeper insights into your application's execution.

Getting Started
---------------

See the :doc:`getting_started` page for installation and basic usage.

API Reference
-------------

See the :doc:`api` page for the full API reference.

Eval-Driven Development
------------------------

See the :doc:`eval_driven_dev` page for more information on how to use Junjo for eval-driven development.