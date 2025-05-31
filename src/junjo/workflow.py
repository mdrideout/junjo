from __future__ import annotations

from abc import ABC, abstractmethod
from types import NoneType
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from opentelemetry import trace

from .node import Node
from .run_concurrent import RunConcurrent
from .store import BaseStore, ParentStateT, ParentStoreT, StateT, StoreT
from .telemetry.hook_manager import HookManager
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from .util import generate_safe_id

if TYPE_CHECKING:
    from .graph import Graph

# Define a covariant TypeVar specifically for the StoreFactory protocol.
# It's bound to BaseStore, ensuring the factory produces BaseStore compatible instances.
_CovariantStoreT = TypeVar("_CovariantStoreT", bound="BaseStore", covariant=True)
class StoreFactory(Protocol, Generic[_CovariantStoreT]):
    def __call__(self, *args, **kw) -> _CovariantStoreT: ...

class _NestableWorkflow(Generic[StateT, StoreT, ParentStateT, ParentStoreT]):
    """
    Represents a workflow execution.
    """

    def __init__(
        self,
        graph: Graph,
        store_factory: StoreFactory[StoreT],
        max_iterations: int = 100,
        hook_manager: HookManager | None = None,
        name: str | None = None,
    ):
        self._id = generate_safe_id()
        self._name = name
        self.graph = graph
        self.max_iterations = max_iterations
        self.node_execution_counter: dict[str, int] = {}
        self.hook_manager = hook_manager

        # Private stores (immutable interactions only)
        self._store_factory = store_factory
        self._store: StoreT | None = None

    @property
    def store(self) -> StoreT:
        if self._store is None:
            raise RuntimeError("Store cannot be accessed before execution. Call execute() first.")
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
        if self._store is None:
            raise RuntimeError("Store cannot be accessed before execution. Call execute() first.")
        return await self._store.get_state()

    async def get_state_json(self) -> str:
        if self._store is None:
            raise RuntimeError("Store cannot be accessed before execution. Call execute() first.")
        return await self._store.get_state_json()

    async def execute(  # noqa: C901
            self,
            parent_store: ParentStoreT | None = None,
            parent_id: str | None = None,
        ):
        """
        Executes the workflow.
        """
        print(f"Executing workflow: {self.name} with ID: {self.id}")

        # TODO: Test that the sink node can be reached

        # Always start with a fresh store for *this* run.
        self._store = self._store_factory()

        # # Execute workflow before hooks
        # if self.hook_manager is not None:
            # self.hook_manager.run_before_workflow_execute_hooks(before_workflow_hook_args)

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            # Set span attributes
            span.set_attribute("junjo.workflow.state.start", await self.get_state_json())
            span.set_attribute("junjo.workflow.graph_structure", self.graph.serialize_to_json_string())
            span.set_attribute("junjo.workflow.store.id", self.store.id)
            span.set_attribute("junjo.span_type", self.span_type)
            span.set_attribute("junjo.id", self.id)

            # Set the parent ID and store ID if available (for subflows)
            if parent_id is not None:
                span.set_attribute("junjo.parent_id", parent_id)

            if parent_store is not None and parent_store.id is not None:
                span.set_attribute("junjo.workflow.parent_store.id", parent_store.id)

            # If executing a subflow, run pre-run actions
            if isinstance(self, Subflow):
                if parent_store is None:
                    raise ValueError("Subflow requires a parent store to execute pre_run_actions.")
                await self.pre_run_actions(parent_store)

            # Loop to execute the nodes inside this workflow
            current_executable = self.graph.source
            try:
                while True:

                    # # Execute node before hooks
                    # if self.hook_manager is not None:
                    #     self.hook_manager.run_before_node_execute_hooks(span_open_node_args)

                    # # If executing a subflow
                    if isinstance(current_executable, Subflow):
                        print("Executing subflow:", current_executable.name)

                        # Pass the current store as the parent store for the sub-flow
                        await current_executable.execute(self.store, self.id)

                        # Incorporate the Subflows node count
                        # into the parent workflow's node execution counter
                        self.node_execution_counter[current_executable.id] = sum(
                            current_executable.node_execution_counter.values()
                        )

                    # If executing a node
                    if isinstance(current_executable, Node):
                        print("Executing node:", current_executable.name)
                        await current_executable.execute(self.store, self.id)

                        # # Execute node after hooks
                        # if self.hook_manager is not None:
                        #     self.hook_manager.run_after_node_execute_hooks(span_close_node_args)

                        # Increment the execution counter for RunConcurrent executions
                        if isinstance(current_executable, RunConcurrent):
                            for item in current_executable.items:
                                self.node_execution_counter[item.id] = self.node_execution_counter.get(item.id, 0) + 1
                                if self.node_execution_counter[item.id] > self.max_iterations:
                                    raise ValueError(
                                        f"Node '{item}' exceeded maximum execution count. \
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


                print(f"Completed workflow: {self.name} with ID: {self.id}")

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

                # Raise the error to be handled by the caller
                raise e

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

# Class Variation
class Workflow(_NestableWorkflow[StateT, StoreT, NoneType, NoneType]):
    """
    Represents a top level workflow that can be executed.

    Generic Type Parameters:
        | StateT: The type of state managed by this workflow
        | StoreT: The type of store used by this workflow

    A workflow is a collection of nodes and edges as a graph that can be executed.

    .. code-block:: python

        workflow = Workflow[MyGraphState, MyGraphStore](
            name="demo_base_workflow",
            graph=graph,
            store=graph_store,
            hook_manager=HookManager(verbose_logging=False, open_telemetry=True),
        )
        await workflow.execute()
    """
    pass

class Subflow(_NestableWorkflow[StateT, StoreT, ParentStateT, ParentStoreT], ABC):
    """
    Represents a subflow execution that can interact with a parent workflow.

    Generic Type Parameters:
        | StateT: The type of state managed by this subflow
        | StoreT: The type of store used by this subflow
        | ParentStateT: The type of state managed by the parent workflow
        | ParentStoreT: The type of store used by the parent workflow

    A subflow is a workflow that:
        | 1. Executes within a parent workflow
        | 2. Has its own isolated state and store
        | 3. Can interact with the parent workflow's state before and after execution

    .. code-block:: python

        class ExampleSubFlow(Subflow[SubflowState, SubflowStore, ParentState, ParentStore]):
            async def pre_run_actions(self, parent_store):
                parent_state = await parent_store.get_state()
                await self.store.set_parameter({
                    "parameter": parent_state.parameter
                })

            async def post_run_actions(self, parent_store):
                async def post_run_actions(self, parent_store):
                    sub_flow_state = await self.get_state()
                    await parent_store.set_subflow_result(self, sub_flow_state.result)
    """

    # def __init__(
    #         self,
    #         graph: Graph,
    #         store: StoreT,
    #         max_iterations: int = 100,
    # ):
    #     """
    #     Initializes the Subflow.

    #     Args:
    #         graph: The workflow graph.
    #         store: The store instance for this subflow.
    #         max_iterations: The maximum number of times a node can be
    #                         executed before raising an exception (defaults to 100)
    #     """
    #     super().__init__(
    #         graph=graph,
    #         store=store,
    #         max_iterations=max_iterations,
    #         hook_manager=None
    #     )

    @abstractmethod
    async def pre_run_actions(self, parent_store: ParentStoreT) -> None:
        """
        This method is called before the workflow has run.

        This is where you can pass initial state values from the parent workflow to the subflow state.

        Args:
            parent_store: The parent store to interact with.

        In this example, we are passing a parameter from the parent store to the subflow store, using
        the subflow's `set_parameter` method, defined in the subflow's store.
        """
        pass

    @abstractmethod
    async def post_run_actions(self, parent_store: ParentStoreT) -> None:
        """
        This method is called after the workflow has run.

        This is where you can update the parent store with the results of the workflow.
        This is useful for subflows that need to update the parent workflow store with their results.

        Args:
            parent_store: The parent store to update.
        """
        pass
