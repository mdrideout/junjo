from __future__ import annotations

from abc import ABC, abstractmethod
from types import NoneType
from typing import TYPE_CHECKING, Generic

from loguru import logger
from opentelemetry import trace

from junjo.node import Node
from junjo.run_concurrent import RunConcurrent
from junjo.store import ParentStateT, ParentStoreT, StateT, StoreT
from junjo.telemetry.hook_manager import HookManager
from junjo.telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from junjo.util import generate_safe_id

if TYPE_CHECKING:
    from junjo.graph import Graph

class _NestableWorkflow(Generic[StateT, StoreT, ParentStateT, ParentStoreT]):
    """
    Represents a workflow execution.
    """

    def __init__(
            self,
            graph: Graph,
            store: StoreT,
            max_iterations: int = 100,
            hook_manager: HookManager | None = None,
            name: str | None = None,
    ):
        """
        Initializes the Workflow.

        Args:
            name: The name of the workflow
            graph: The workflow graph.
            max_iterations: The maximum number of times a node can be
                            executed before raising an exception (defaults to 100)

        """
        self._id = generate_safe_id()
        self._name = name
        self.graph = graph
        self.max_iterations = max_iterations
        self.node_execution_counter: dict[str, int] = {}
        self.hook_manager = hook_manager

        # Private stores (immutable interactions only)
        self._store = store

    @property
    def store(self) -> StoreT:
        return self._store

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @property
    def name(self) -> str:
        """Returns the name of the node class instance."""
        if self._name is not None:
            return self._name

        return self.__class__.__name__

    @property
    def span_type(self) -> JunjoOtelSpanTypes:
        """Returns the span type of the workflow."""

        if isinstance(self, Subflow):
            return JunjoOtelSpanTypes.SUBFLOW
        return JunjoOtelSpanTypes.WORKFLOW

    async def get_state(self) -> StateT:
        return await self._store.get_state()

    async def get_state_json(self) -> str:
        return await self._store.get_state_json()

    async def execute(  # noqa: C901
            self,
            parent_store: ParentStoreT | None = None,
            parent_id: str | None = None,
        ):
        """
        Executes the workflow.
        """
        logger.info(f"Executing workflow: {self.name} with ID: {self.id}")

        # TODO: Test that the sink node can be reached

        # # Execute workflow before hooks
        # if self.hook_manager is not None:
            # self.hook_manager.run_before_workflow_execute_hooks(before_workflow_hook_args)

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            span.set_attribute("junjo.workflow.state.start", await self.get_state_json())
            span.set_attribute("junjo.workflow.graph_structure", self.graph.serialize_to_json_string())
            span.set_attribute("junjo.workflow.store.id", self.store.id)
            span.set_attribute("junjo.span_type", self.span_type)
            span.set_attribute("junjo.id", self.id)

            if parent_id is not None:
                span.set_attribute("junjo.parent_id", parent_id)

            # Loop to execute the nodes inside this workflow
            current_executable = self.graph.source
            try:
                while True:
                    try:
                        # # Execute node before hooks
                        # if self.hook_manager is not None:
                        #     self.hook_manager.run_before_node_execute_hooks(span_open_node_args)

                        # # If executing a subflow
                        if isinstance(current_executable, Subflow):
                            print("Executing subflow:", current_executable.name)
                            # Pass the current store as the parent store for the sub-flow
                            await current_executable.execute(self.store, self.id)

                        # If executing a node
                        if isinstance(current_executable, Node):
                            print("Executing node:", current_executable.name)
                            await current_executable.execute(self.store, self.id)

                            # # Execute node after hooks
                            # if self.hook_manager is not None:
                            #     self.hook_manager.run_after_node_execute_hooks(span_close_node_args)

                            # Increment the execution counter for RunConcurrent executions
                            if isinstance(current_executable, RunConcurrent):
                                for node in current_executable.items:
                                    self.node_execution_counter[node.id] = self.node_execution_counter.get(node.id, 0) + 1
                                    if self.node_execution_counter[node.id] > self.max_iterations:
                                        raise ValueError(
                                            f"Node '{node}' exceeded maximum execution count. \
                                            Check for loops in your graph. Ensure it transitions to the sink node."
                                        )

                            # Increment the execution counter for Node executions
                            else:
                                self.node_execution_counter[current_executable.id] = self.node_execution_counter.get(current_executable.id, 0) + 1
                                if self.node_execution_counter[current_executable.id] > self.max_iterations:
                                    raise ValueError(
                                        f"Node '{current_executable}' exceeded maximum execution count. \
                                        Check for loops in your graph. Ensure it transitions to the sink node."
                                    )

                        # Break the loop if the current node is the final node.
                        if current_executable == self.graph.sink:
                            print("Sink has executed. Exiting loop.")
                            break

                        # Get the next executable in the workflow.
                        current_executable = await self.graph.get_next_node(self.store, current_executable)

                    except Exception as e:
                        print(f"Error executing node: {e}")
                        raise e

                logger.info(f"Completed workflow: {self.name} with ID: {self.id}")

                # Perform subflow post-run actions
                if isinstance(self, Subflow):
                    if parent_store is None:
                        raise ValueError("Subflow requires a parent store to execute post_run_actions.")
                    else:
                        print("Performing post-run actions for subflow:", self.name)
                        await self.post_run_actions(parent_store)

            except Exception as e:
                print(f"Error executing workflow: {e}")
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)

            finally:
                execution_sum = sum(self.node_execution_counter.values())

                # Update attributes *after* the workflow loop completes (or errors)
                span.set_attribute("junjo.workflow.state.end", await self.get_state_json())
                span.set_attribute("junjo.workflow.node.count", execution_sum)

            # # Execute workflow after hooks
            # if self.hook_manager is not None:
            #     self.hook_manager.run_after_workflow_execute_hooks(
            #         after_workflow_hook_args
            #     )

            return

# Type Aliases
# Workflow: TypeAlias = _NestableWorkflow[StateT, StoreT, NoneType, NoneType]
# Subflow: TypeAlias = _NestableWorkflow[StateT, StoreT, ParentStateT, ParentStoreT]

# Class Variation
class Workflow(_NestableWorkflow[StateT, StoreT, NoneType, NoneType]):
    """
    Represents a workflow execution.
    """
    pass

class Subflow(_NestableWorkflow[StateT, StoreT, ParentStateT, ParentStoreT], ABC):
    """
    Represents a subflow execution that can interact with a parent workflow.

    Generic Type Parameters:
        StateT: The type of state managed by this subflow
        StoreT: The type of store used by this subflow
        ParentStateT: The type of state managed by the parent workflow
        ParentStoreT: The type of store used by the parent workflow

    A subflow is a workflow that:
    1. Executes within a parent workflow
    2. Has its own isolated state and store
    3. Can update the parent workflow's store after completion via post_run_actions
    """

    def __init__(
            self,
            graph: Graph,
            store: StoreT,
            max_iterations: int = 100,
    ):
        """
        Initializes the Subflow.

        Args:
            graph: The workflow graph.
            store: The store instance for this subflow.
            max_iterations: The maximum number of times a node can be
                            executed before raising an exception (defaults to 100)
        """
        super().__init__(
            graph=graph,
            store=store,
            max_iterations=max_iterations,
            hook_manager=None
        )

    @abstractmethod
    async def post_run_actions(self, parent_store: ParentStoreT) -> None:
        """
        # Post Run Actions
        This method is called after the workflow has run.

        This is where you can update the parent store with the results of the workflow.
        This is useful for subflows that need to update the parent workflow store with their results.

        Example:
            ```python
                async def post_run_actions(self, parent_store):
                    # Get the parent store
                    sub_flow_state = await self.get_state()

                    # Update the parent store with values from the SubFlow state
                    await parent_store.set_subflow_result(self, sub_flow_state.result)
            ```

        Args:
            parent_store: The parent store to update.
        """
        pass
