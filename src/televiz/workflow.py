from typing import Any

from televiz.graph import Graph


class Workflow:
    """
    Represents a workflow execution.
    """

    def __init__(self, graph: Graph, context: dict[str, Any] = {}, max_iterations: int = 100):
        """
        Initializes the Workflow.

        Args:
            graph: The workflow graph.
            context: The initial workflow context (a dictionary).
            max_iterations: The maximum number of times a node can be
                            executed before raising an exception (defaults to 100)

        """
        self.graph = graph
        self.context = context or {}
        self.max_iterations = max_iterations
        self.node_execution_counter: dict[str, int] = {}

    async def execute(self):
        """
        Executes the workflow.
        """

        current_node = self.graph.source

        while current_node != self.graph.sink: # Check if the sink node has been reached.
            try:
                await current_node.execute()
                self.context.update(current_node.outputs)

                # Increment the execution counter for the current node.
                self.node_execution_counter[current_node.id] = self.node_execution_counter.get(current_node.id, 0) + 1
                if self.node_execution_counter[current_node.id] > self.max_iterations:
                    raise ValueError(f"Node '{current_node}' exceeded maximum execution count. Check for loops.")

                # Get the next node in the workflow.
                current_node = self.graph.get_next_node(current_node, self.context)

            # re-raise the value error
            except ValueError as e:
                raise e

            except Exception as e:
                print(f"Error executing node: {e}")
                break  # Or handle the error more robustly
