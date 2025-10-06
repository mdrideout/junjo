# Junjo Library Overview for LLM Agents

This document provides a concise overview of the Junjo library, designed to give LLM agents the necessary context to understand, modify, and extend the codebase.

## High-Level Summary

Junjo is a Python library for building and managing complex, graph-based AI workflows. It is designed to be consumed by Python application developers. The library provides a framework for defining workflows as a series of nodes and edges, managing state in a predictable and concurrency-safe manner, and visualizing the workflow's structure and execution.

**Key Use Cases:**

*   Building complex LLM-powered agents and applications.
*   Orchestrating data processing pipelines.
*   Creating workflows with conditional branching and parallel execution.

## Core Concepts

The following are the fundamental building blocks of the Junjo library:

### 1. `State` and `Store`

*   **`BaseState` (`src/junjo/state.py`):** A Pydantic `BaseModel` that defines the data structure for a workflow's state. All workflow states must inherit from this class.
*   **`BaseStore` (`src/junjo/store.py`):** A class that manages the state of a workflow. It holds the `BaseState` and provides methods (actions) to update the state in a controlled and predictable manner. It uses an `asyncio.Lock` to ensure that state updates are atomic and concurrency-safe.

**Example:**

```python
from junjo import BaseState, BaseStore

class MyWorkflowState(BaseState):
    user_input: str
    processed_data: dict | None = None

class MyWorkflowStore(BaseStore[MyWorkflowState]):
    async def set_processed_data(self, data: dict) -> None:
        await self.set_state({"processed_data": data})
```

### 2. `Node`

*   **`Node` (`src/junjo/node.py`):** An abstract base class that represents a single unit of work in a workflow. The business logic is implemented in the `service` method. Nodes interact with the `Store` to get and set state.

**Example:**

```python
from junjo import Node

class ProcessDataNode(Node[MyWorkflowStore]):
    async def service(self, store: MyWorkflowStore) -> None:
        state = await store.get_state()
        processed_data = {"result": "some_value"}
        await store.set_processed_data(processed_data)
```

### 3. `Edge` and `Condition`

*   **`Edge` (`src/junjo/edge.py`):** Defines a directed connection between two nodes (`tail` and `head`) in a workflow graph.
*   **`Condition` (`src/junjo/condition.py`):** An abstract base class for implementing conditional logic on an `Edge`. The `evaluate` method determines if a transition between nodes should occur based on the current state.

**Example:**

```python
from junjo import Edge, Condition

class DataIsProcessed(Condition[MyWorkflowState]):
    def evaluate(self, state: MyWorkflowState) -> bool:
        return state.processed_data is not None

edge = Edge(tail=node1, head=node2, condition=DataIsProcessed())
```

### 4. `Graph`

*   **`Graph` (`src/junjo/graph.py`):** A collection of nodes and edges that defines the complete structure of a workflow. It has a single entry point (`source`) and a single exit point (`sink`).

**Example:**

```python
from junjo import Graph

workflow_graph = Graph(
    source=start_node,
    sink=end_node,
    edges=[
        Edge(tail=start_node, head=process_node),
        Edge(tail=process_node, head=end_node, condition=DataIsProcessed())
    ]
)
```

### 5. `Workflow` and `Subflow`

*   **`Workflow` (`src/junjo/workflow.py`):** The main executable component that takes a `graph_factory` and a `store_factory` and runs the defined process.
*   **`Subflow` (`src/junjo/workflow.py`):** A workflow that can be nested within another workflow, allowing for modular and reusable logic. It has its own isolated state and can interact with its parent's state via `pre_run_actions` and `post_run_actions`.

### 6. `RunConcurrent`

*   **`RunConcurrent` (`src/junjo/run_concurrent.py`):** A special type of `Node` that allows for the parallel execution of multiple nodes or subflows using `asyncio.gather`.

## Key Design Patterns

*   **Asyncio-native:** The library is built on top of Python's `asyncio`, enabling non-blocking I/O operations and efficient concurrency.
*   **Immutable State Management:** Inspired by Redux, state is treated as immutable. State changes are made by calling methods on the `Store`, which creates a new state object with the updates. This ensures predictable state transitions and concurrency safety.
*   **Dependency Injection via Factories:** `Workflow` and `Subflow` are initialized with `graph_factory` and `store_factory` callables. This ensures that each workflow execution gets a fresh, isolated graph and store, which is critical for concurrency safety.

## How to...

### Create a new Node

1.  Create a new class that inherits from `junjo.Node`.
2.  Specify the `Store` type as a generic parameter.
3.  Implement the `async def service(self, store: StoreT) -> None:` method with your business logic.

### Add a Condition to an Edge

1.  Create a new class that inherits from `junjo.Condition`.
2.  Specify the `State` type as a generic parameter.
3.  Implement the `def evaluate(self, state: StateT) -> bool:` method.
4.  Instantiate the condition and pass it to the `condition` parameter of the `Edge`.

### Create a Subflow

1.  Create a new class that inherits from `junjo.Subflow`.
2.  Specify the `SubflowState`, `SubflowStore`, `ParentState`, and `ParentStore` types as generic parameters.
3.  Implement the `pre_run_actions` and `post_run_actions` methods to interact with the parent store.
4.  Instantiate the subflow with its own `graph_factory` and `store_factory`.

## Important Files

*   `src/junjo/workflow.py`: Contains the core logic for workflow and subflow execution.
*   `src/junjo/graph.py`: Defines the structure of a workflow.
*   `src/junjo/node.py`: Defines the base class for all nodes.
*   `src/junjo/store.py`: Contains the base class for state management.
*   `src/junjo/edge.py`: Defines the connection between nodes.
*   `src/junjo/condition.py`: Defines the base class for conditional logic.