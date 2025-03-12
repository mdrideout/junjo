
import time
from typing import Generic

from nanoid import generate

from junjo.app import JunjoApp
from junjo.graph import Graph
from junjo.store import BaseStore, StateT, StoreT
from junjo.telemetry.hook_manager import HookManager
from junjo.telemetry.junjo_server.client import JunjoUiClient, WorkflowLogType
from junjo.workflow_context import WorkflowContextManager


class Workflow(Generic[StateT, StoreT]):
    """
    Represents a workflow execution.
    """

    def __init__(
            self,
            workflow_name: str,
            graph: Graph,
            initial_store: BaseStore,
            max_iterations: int = 100,
            hook_manager: HookManager | None = None,
            parent_workflow_id: str | None = None
    ):
        """
        Initializes the Workflow.

        Args:
            name: The name of the workflow
            graph: The workflow graph.
            context: The initial workflow context (a dictionary).
            max_iterations: The maximum number of times a node can be
                            executed before raising an exception (defaults to 100)

        """
        self.workflow_id = generate()
        self.workflow_name = workflow_name.strip()
        self.graph = graph
        self.max_iterations = max_iterations
        self.node_execution_counter: dict[str, int] = {}
        self.hook_manager = hook_manager
        self.parent_workflow_id = parent_workflow_id

        # Set up a store for this workflow
        WorkflowContextManager.set_store(self.workflow_id, initial_store)

    @property
    def get_store(self) -> BaseStore | None:
        """Returns the current store from the context var."""
        store = WorkflowContextManager.get_store(self.workflow_id)
        return store

    @property
    def get_state(self) -> StateT | None:
        """Returns the current store state from the context var."""
        store = WorkflowContextManager.get_store(self.workflow_id)
        return store.get_state() if store else None

    @property
    def get_state_json(self) -> str:
        """Returns the current store state as a JSON string from the context var."""
        store = WorkflowContextManager.get_store(self.workflow_id)
        return store.get_state_json()

    async def execute(self):
        """
        Executes the workflow.
        """
        # TODO: Test that the sink node can be reached

        # Execute workflow before hooks
        if self.hook_manager is not None:
            workflow_start_time = time.time()
            workflow_start_time_ns = time.time_ns()

            # TEST Junjo UI Client - Workflow Metadata
            exec_id = self.workflow_id
            app_name = JunjoApp().app_name
            workflow_name = self.workflow_name
            event_time_nano = workflow_start_time_ns
            structure = self.graph.serialize_to_json_string()
            print("Sending structure to Junjo UI Client:", structure)
            JunjoUiClient().create_workflow_metadata(
                exec_id,
                app_name,
                workflow_name,
                event_time_nano,
                structure,
            )

            # TEST Junjo UI Client - Workflow Log Start
            exec_id = self.workflow_id
            type = WorkflowLogType.START
            state_json = self.get_state_json
            print("Sending state_json to Junjo UI Client:", state_json)
            JunjoUiClient().create_workflow_log(exec_id, type, event_time_nano, state_json)

            # Execute the before workflow hooks
            self.hook_manager.run_before_workflow_execute_hooks(self.workflow_id)


        current_node = self.graph.source
        while True:
            try:
                # Execute node before hooks
                if self.hook_manager is not None:
                    self.hook_manager.run_before_node_execute_hooks(self.workflow_id, current_node.id, self.get_state)
                    node_start_time = time.time()

                # Execute the current node.
                print("Executing node:", current_node.id)
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
                    raise ValueError(
                        f"Node '{current_node}' exceeded maximum execution count. \
                        Check for loops in your graph. Ensure it transitions to the sink node."
                    )

                # Break the loop if the current node is the final node.
                if current_node == self.graph.sink:
                    print("Sink has executed. Exiting loop.")
                    break

                # Get the next node in the workflow.
                current_node = self.graph.get_next_node(self.workflow_id, current_node)

            except Exception as e:
                print(f"Error executing node: {e}")
                raise e

        # Execute workflow after hooks
        if self.hook_manager is not None:
            workflow_end_time = time.time()
            workflow_end_time_ns = time.time_ns()

            # TEST Junjo UI Client - Workflow Log End
            exec_id = self.workflow_id
            type = WorkflowLogType.END
            event_time_nano = workflow_end_time_ns
            state_json = self.get_state_json
            JunjoUiClient().create_workflow_log(exec_id, type, event_time_nano, state_json)

            # Execute the after workflow hooks
            self.hook_manager.run_after_workflow_execute_hooks(
                self.workflow_id,
                self.get_state,
                workflow_end_time - workflow_start_time
            )

        return
