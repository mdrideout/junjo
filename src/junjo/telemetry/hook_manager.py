from collections.abc import Callable

from junjo.telemetry.hook_schema import (
    SpanCloseSchemaNode,
    SpanCloseSchemaWorkflow,
    SpanOpenSchemaNode,
    SpanOpenSchemaWorkflow,
)


class HookManager:
    def __init__(self, verbose_logging: bool = False, open_telemetry: bool = False):
        self.before_workflow_execute_hooks = []
        self.after_workflow_execute_hooks = []
        self.before_node_execute_hooks = []
        self.after_node_execute_hooks = []

        if verbose_logging:
            self.register_verbose_hooks()

        # if open_telemetry:
        #     self.register_open_telemetry_hooks()


    # Workflow Execution Hooks
    def add_before_workflow_execute_hook(self, hook: Callable[[SpanOpenSchemaWorkflow], None]):
        self.before_workflow_execute_hooks.append(hook)

    def add_after_workflow_execute_hook(self, hook: Callable[[SpanCloseSchemaWorkflow], None]):
        self.after_workflow_execute_hooks.append(hook)

    def run_before_workflow_execute_hooks(self, args: SpanOpenSchemaWorkflow):
        for hook in self.before_workflow_execute_hooks:
            hook(args)

    def run_after_workflow_execute_hooks(self, args: SpanCloseSchemaWorkflow):
        for hook in self.after_workflow_execute_hooks:
            hook(args)


    # Node Execution Hooks
    def add_before_node_execute_hook(self, hook: Callable[[SpanOpenSchemaNode], None]):
        self.before_node_execute_hooks.append(hook)

    def add_after_node_execute_hook(self, hook: Callable[[SpanCloseSchemaNode], None]):
        self.after_node_execute_hooks.append(hook)

    def run_before_node_execute_hooks(self, args: SpanOpenSchemaNode):
        for hook in self.before_node_execute_hooks:
            hook(args)

    def run_after_node_execute_hooks(self, args: SpanCloseSchemaNode):
        for hook in self.after_node_execute_hooks:
            hook(args)

    def register_verbose_hooks(self) -> None:
        """Verbose hooks introduce verbose logging into the workflow execution lifecycle."""
        def log_before_workflow_execute(args: SpanOpenSchemaWorkflow):
            print(f"\nBefore Executing Workflow: {args.junjo_id}")

        def log_after_workflow_execute(args: SpanCloseSchemaWorkflow):
            print(f"After Executing Workflow: {args.junjo_id}")

        def log_before_node_execute(args: SpanOpenSchemaNode):
            print(f"\nBefore Executing: {args.junjo_id} (workflow: {args.junjo_workflow_id})")

        def log_after_node_execute(args: SpanCloseSchemaNode):
            print(f"After Executing: {args.junjo_id}")


        self.add_before_workflow_execute_hook(log_before_workflow_execute)
        self.add_after_workflow_execute_hook(log_after_workflow_execute)
        self.add_before_node_execute_hook(log_before_node_execute)
        self.add_after_node_execute_hook(log_after_node_execute)

    # def register_open_telemetry_hooks(self) -> None:
    #     """Registers the OpenTelemetry hooks with the HookManager."""
    #     otel_hooks = OpenTelemetryHooks(service_name="test_service_name", host="localhost", port="4317")
    #     self.add_before_workflow_execute_hook(otel_hooks.before_workflow_execute)
    #     self.add_after_workflow_execute_hook(otel_hooks.after_workflow_execute)
        # self.add_before_node_execute_hook(otel_hooks.before_node_execute)
        # self.add_after_node_execute_hook(otel_hooks.after_node_execute)
