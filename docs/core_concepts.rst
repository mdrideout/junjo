.. _core_concepts:

##############################################################
Core Concepts
##############################################################

.. meta::
    :description: Understand the core concepts of Junjo, including State, Store, Node, Edge, Condition, Graph, and Workflow. Learn how these components work together to build powerful and scalable Python workflows.
    :keywords: junjo, python, workflow, state management, node, edge, graph, core concepts

This page breaks down the fundamental building blocks of the Junjo library. Understanding these concepts is key to effectively designing, building, and debugging your workflows.

State
=====

**What is it?**
A `BaseState` is a Pydantic model that defines the data structure for your workflow's state. It acts as a centralized, type-safe container for all the data that your workflow will operate on.

**Key Characteristics:**
- **Pydantic-Based:** Leverages Pydantic for data validation and type hinting.
- **Immutable in Practice:** While the state object itself can be replaced, it is treated as immutable within the workflow. Nodes do not modify the state directly; they request changes through the store.

.. code-block:: python

    from junjo import BaseState

    class MyWorkflowState(BaseState):
        user_input: str
        processed_data: dict | None = None
        is_complete: bool = False

Store
=====

**What is it?**
A `BaseStore` is a class that manages the state of a workflow. It holds the `BaseState` and provides methods (often called "actions") to update the state in a controlled and predictable manner.

**Key Characteristics:**
- **State Management:** The single source of truth for the workflow's state.
- **Redux-Inspired:** Follows a pattern where state is updated by dispatching actions, ensuring that state changes are explicit and traceable.
- **Concurrency Safe:** Uses an `asyncio.Lock` to ensure that state updates are atomic, preventing race conditions.

.. code-block:: python

    from junjo import BaseStore

    class MyWorkflowStore(BaseStore[MyWorkflowState]):
        async def set_processed_data(self, data: dict) -> None:
            await self.set_state({"processed_data": data})

        async def mark_as_complete(self) -> None:
            await self.set_state({"is_complete": True})

Node
====

**What is it?**
A `Node` represents a single unit of work in your workflow. It's where your business logic, API calls, or any other operations are executed.

**Key Characteristics:**
- **Atomic Unit of Work:** Each node should have a single, well-defined responsibility.
- **Interacts with the Store:** Nodes receive the workflow's store as an argument to their `service` method, allowing them to read the current state and dispatch actions to update it.
- **Asynchronous:** The `service` method is an `async` function, allowing for non-blocking I/O operations.

.. code-block:: python

    from junjo import Node

    class ProcessDataNode(Node[MyWorkflowStore]):
        async def service(self, store: MyWorkflowStore) -> None:
            state = await store.get_state()
            # Perform some processing on state.user_input
            processed_data = {"result": "some_value"}
            await store.set_processed_data(processed_data)

Edge
====

**What is it?**
An `Edge` defines a directed connection between two nodes in a workflow graph. It represents a potential path of execution.

**Key Characteristics:**
- **Defines Flow:** Edges connect a `tail` node to a `head` node, establishing the sequence of operations.
- **Can be Conditional:** An edge can have an associated `Condition` that determines whether the transition from the tail to the head should occur.

.. code-block:: python

    from junjo import Edge

    edge = Edge(tail=node1, head=node2)

Condition
=========

**What is it?**
A `Condition` is a class that contains logic to determine whether an `Edge` should be traversed.

**Key Characteristics:**
- **Pure Function of State:** A condition's `evaluate` method should only depend on the current state of the workflow. It should not have any side effects.
- **Enables Branching:** Conditions are the primary mechanism for creating branching logic in your workflows.

.. code-block:: python

    from junjo import Condition

    class DataIsProcessed(Condition[MyWorkflowState]):
        def evaluate(self, state: MyWorkflowState) -> bool:
            return state.processed_data is not None

    edge = Edge(tail=node1, head=node2, condition=DataIsProcessed())

Graph
=====

**What is it?**
A `Graph` is a collection of nodes and edges that defines the complete structure of your workflow.

**Key Characteristics:**
- **Source and Sink:** A graph has a single entry point (`source`) and a single exit point (`sink`).
- **Defines the Workflow Structure:** The graph is a complete representation of all possible paths of execution in your workflow.

.. code-block:: python

    from junjo import Graph

    workflow_graph = Graph(
        source=start_node,
        sink=end_node,
        edges=[
            Edge(tail=start_node, head=process_node),
            Edge(tail=process_node, head=end_node, condition=DataIsProcessed())
        ]
    )

Workflow
========

**What is it?**
A `Workflow` is the main executable component that takes a `graph_factory` and a `store_factory` and runs the defined process.

**Key Characteristics:**
- **Executable:** The `Workflow` class has an `execute` method that starts the workflow.
- **Manages Execution:** It traverses the graph, executing nodes and evaluating conditions, until the `sink` node is reached.
- **Isolated Execution:** Each call to `execute` uses the provided factories to create a fresh `Graph` and `Store`, ensuring that each execution is isolated and concurrency-safe.

.. code-block:: python

    from junjo import Workflow

    def create_graph() -> Graph:
        # ... (graph creation logic)
        return workflow_graph

    sample_workflow = Workflow[MyWorkflowState, MyWorkflowStore](
        name="My First Workflow",
        graph_factory=create_graph,
        store_factory=lambda: MyWorkflowStore(
            initial_state=MyWorkflowState(user_input="hello")
        )
    )

    await sample_workflow.execute()