from collections.abc import Callable
from typing import Any


class TelemetryManager:
    def __init__(self, verbose_logging: bool = False):
        self.before_execution_hooks = []
        self.after_execution_hooks = []

        if verbose_logging:
            self.register_verbose_hooks()

    def add_before_execution_hook(self, hook: Callable[[str, Any], None]):
        self.before_execution_hooks.append(hook)

    def add_after_execution_hook(self, hook: Callable[[str, Any, float], None]):
        self.after_execution_hooks.append(hook)

    def execute_before_hooks(self, node_id: str, state: Any):
        for hook in self.before_execution_hooks:
            hook(node_id, state)

    def execute_after_hooks(self, node_id: str, state: Any, duration: float):
        for hook in self.after_execution_hooks:
            hook(node_id, state, duration)

    def register_verbose_hooks(self) -> None:
        def log_before_execution(node_id: str, state: Any):
            print(f"\nBefore Executing: {node_id} | State: {state}")

        def log_after_execution(node_id: str, state: Any, duration: float):
            duration_ms = duration * 1000
            print(f"After Executing: {node_id} | State: {state}\n(Duration: {duration_ms:.5f}ms)\n")

        self.add_before_execution_hook(log_before_execution)
        self.add_after_execution_hook(log_after_execution)
