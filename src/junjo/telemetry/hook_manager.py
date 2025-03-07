from collections.abc import Callable
from typing import Any

from junjo.telemetry.opentelemetry_hooks import OpenTelemetryHooks


class HookManager:
    def __init__(self, verbose_logging: bool = False, open_telemetry: bool = False):
        self.before_workflow_execute_hooks = []
        self.after_workflow_execute_hooks = []
        self.before_node_execute_hooks = []
        self.after_node_execute_hooks = []

        if verbose_logging:
            self.register_verbose_hooks()

        if open_telemetry:
            self.register_open_telemetry_hooks()


    # Workflow Execution Hooks
    def add_before_workflow_execute_hook(self, hook: Callable[[str], None]):
        self.before_workflow_execute_hooks.append(hook)

    def add_after_workflow_execute_hook(self, hook: Callable[[str, Any, float], None]):
        self.after_workflow_execute_hooks.append(hook)

    def run_before_workflow_execute_hooks(self, workflow_id: str):
        for hook in self.before_workflow_execute_hooks:
            hook(workflow_id)

    def run_after_workflow_execute_hooks(self, workflow_id: str, state: Any, duration: float):
        for hook in self.after_workflow_execute_hooks:
            hook(workflow_id, state, duration)


    # Node Execution Hooks
    def add_before_node_execute_hook(self, hook: Callable[[str, str, Any], None]):
        self.before_node_execute_hooks.append(hook)

    def add_after_node_execute_hook(self, hook: Callable[[str, Any, float], None]):
        self.after_node_execute_hooks.append(hook)

    def run_before_node_execute_hooks(self, workflow_id: str, node_id: str, state: Any):
        for hook in self.before_node_execute_hooks:
            hook(workflow_id, node_id, state)

    def run_after_node_execute_hooks(self, node_id: str, state: Any, duration: float):
        for hook in self.after_node_execute_hooks:
            hook(node_id, state, duration)

    def register_verbose_hooks(self) -> None:
        """Verbose hooks introduce verbose logging into the workflow execution lifecycle."""
        def log_before_workflow_execute(workflow_id: str):
            print(f"\nBefore Executing Workflow: {workflow_id}")

        def log_after_workflow_execute(workflow_id: str, state: Any, duration: float):
            duration_ms = duration * 1000
            print(f"After Executing Workflow: {workflow_id} | State: {state}\n(Duration: {duration_ms:.5f}ms)\n")

        def log_before_node_execute(workflow_id: str, node_id: str, state: Any):
            print(f"\nBefore Executing: {node_id} (workflow: {workflow_id}) | State: {state}")

        def log_after_node_execute(node_id: str, state: Any, duration: float):
            duration_ms = duration * 1000
            print(f"After Executing: {node_id} | State: {state}\n(Duration: {duration_ms:.5f}ms)\n")


        self.add_before_workflow_execute_hook(log_before_workflow_execute)
        self.add_after_workflow_execute_hook(log_after_workflow_execute)
        self.add_before_node_execute_hook(log_before_node_execute)
        self.add_after_node_execute_hook(log_after_node_execute)

    def register_open_telemetry_hooks(self) -> None:
        """Registers the OpenTelemetry hooks with the HookManager."""
        otel_hooks = OpenTelemetryHooks(service_name="test_service_name", jaeger_host="localhost", jaeger_port=4317)
        self.add_before_workflow_execute_hook(otel_hooks.before_workflow_execute)
        self.add_after_workflow_execute_hook(otel_hooks.after_workflow_execute)
        self.add_before_node_execute_hook(otel_hooks.before_node_execute)
        self.add_after_node_execute_hook(otel_hooks.after_node_execute)
