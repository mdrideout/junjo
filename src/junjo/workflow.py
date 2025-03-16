
from typing import Generic

from nanoid import generate
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span

from junjo.graph import Graph
from junjo.store import StateT, StoreT
from junjo.telemetry.hook_manager import HookManager
from junjo.telemetry.otel_provider import OpenTelemetryProvider
from junjo.telemetry.otel_schema import JunjoOtelSpanTypes


class Workflow(Generic[StateT, StoreT]):
    """
    Represents a workflow execution.
    """

    def __init__(
            self,
            workflow_name: str,
            graph: Graph,
            store: StoreT,
            max_iterations: int = 100,
            hook_manager: HookManager | None = None,
            otel_provider: OpenTelemetryProvider | None = None,
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
        self.otel_provider = otel_provider
        self.parent_workflow_id = parent_workflow_id

        # Private store (immutable interactions only)
        self._store = store

    @property
    def store(self) -> StoreT:
        return self._store

    async def get_state(self) -> StateT:
        return await self._store.get_state()

    async def get_state_json(self) -> str:
        return await self._store.get_state_json()

    async def execute(self):
        """
        Executes the workflow.
        """
        # TODO: Test that the sink node can be reached

        # # Execute workflow before hooks
        # if self.hook_manager is not None:
            # self.hook_manager.run_before_workflow_execute_hooks(before_workflow_hook_args)

        # IF otel: open the workflow span
        if self.otel_provider is not None:
            span = self._otel_span_open(self.otel_provider)
            span.set_attribute("junjo.workflow.state.start", await self.get_state_json())

            with trace.use_span(span, end_on_exit=True):
                current_context = trace.get_current_span().get_span_context()
                # Convert trace context to a context that can be passed to start_span
                current_context = trace.set_span_in_context(trace.get_current_span(), otel_context.get_current())

                current_node = self.graph.source
                try:
                    while True:
                        try:
                            # # Execute node before hooks
                            # if self.hook_manager is not None:
                            #     self.hook_manager.run_before_node_execute_hooks(span_open_node_args)

                            # Execute the current node.
                            print("Executing node:", current_node.name)
                            await current_node._execute(self.store, self.otel_provider, current_context)

                            # # Execute node after hooks
                            # if self.hook_manager is not None:
                            #     self.hook_manager.run_after_node_execute_hooks(span_close_node_args)

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
                            current_node = await self.graph.get_next_node(self.store, current_node)

                        except Exception as e:
                            span.set_status(trace.StatusCode.ERROR, str(e))
                            span.record_exception(e)
                            print(f"Error executing node: {e}")
                            raise e

                    span.set_status(trace.StatusCode.OK)

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

    def _otel_span_open(self, otel: OpenTelemetryProvider) -> Span:
        """Open the Node's OpenTelemetry span."""
        print(f"Opening span for {self.workflow_name}")

        tracer = otel.get_tracer()
        span = tracer.start_span(name=self.workflow_name)
        span.set_attribute("junjo.span_type", JunjoOtelSpanTypes.WORKFLOW)
        span.set_attribute("junjo.workflow_id", self.workflow_id)

        if self.parent_workflow_id is not None:
            span.set_attribute("junjo.parent_workflow_id", self.parent_workflow_id)

        return span
