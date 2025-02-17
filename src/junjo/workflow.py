
import time
from typing import Generic

from nanoid import generate

from junjo.graph import Graph
from junjo.store import BaseStore, StateT, StoreT
from junjo.telemetry.hook_manager import HookManager
from junjo.workflow_context import WorkflowContextManager


class Workflow(Generic[StateT, StoreT]):
    """
    Represents a workflow execution.
    """

    def __init__(
            self,
            graph: Graph,
            initial_store: BaseStore,
            max_iterations: int = 100,
            hook_manager: HookManager | None = None
    ):
        """
        Initializes the Workflow.

        Args:
            graph: The workflow graph.
            context: The initial workflow context (a dictionary).
            max_iterations: The maximum number of times a node can be
                            executed before raising an exception (defaults to 100)

        """
        self.workflow_id = generate()
        self.graph = graph
        self.max_iterations = max_iterations
        self.node_execution_counter: dict[str, int] = {}
        self.hook_manager = hook_manager

        # Set up a store for this workflow
        WorkflowContextManager.set_store(self.workflow_id, initial_store)

    @property
    def get_store(self) -> StoreT | None:
        """Returns the current store from the context var."""
        store = WorkflowContextManager.get_store(self.workflow_id)
        return store

    @property
    def get_state(self) -> StateT | None:
        """Returns the current store state from the context var."""
        store = WorkflowContextManager.get_store(self.workflow_id)
        return store.get_state() if store else None

    async def execute(self):
        """
        Executes the workflow.
        """
        # Execute workflow before hooks
        if self.hook_manager is not None:
            self.hook_manager.run_before_workflow_execute_hooks(self.workflow_id)
            workflow_start_time = time.time()

        current_node = self.graph.source
        while current_node != self.graph.sink: # Check if the sink node has been reached.
            try:
                # Execute node before hooks
                if self.hook_manager is not None:
                    self.hook_manager.run_before_node_execute_hooks(current_node.id, self.get_state)
                    node_start_time = time.time()

                # Execute the current node.
                await current_node._execute(self.workflow_id)

                # Execute node after hooks
                if self.hook_manager is not None:
                    node_end_time = time.time()
                    self.hook_manager.run_after_node_execute_hooks(
                        current_node.id,
                        self.get_state,
                        node_end_time - node_start_time
                    )

                # Increment the execution counter for the current node.
                self.node_execution_counter[current_node.id] = self.node_execution_counter.get(current_node.id, 0) + 1
                if self.node_execution_counter[current_node.id] > self.max_iterations:
                    raise ValueError(f"Node '{current_node}' exceeded maximum execution count. Check for loops.")

                # Get the next node in the workflow.
                current_node = self.graph.get_next_node(self.workflow_id, current_node)

            except Exception as e:
                print(f"Error executing node: {e}")
                raise e

        # Execute workflow after hooks
        if self.hook_manager is not None:
            workflow_end_time = time.time()
            self.hook_manager.run_after_workflow_execute_hooks(
                self.workflow_id,
                self.get_state,
                workflow_end_time - workflow_start_time
            )
