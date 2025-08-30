from junjo import Edge, Graph

from base.sample_workflow.sample_subflow.nodes.create_fact_node.node import CreateFactNode
from base.sample_workflow.sample_subflow.nodes.create_joke_node.node import CreateJokeNode


def create_sample_subflow_graph() -> Graph:
    """
    Factory function to create a new instance of the sample subflow graph.
    """
    # Instantiate the nodes
    create_joke_node = CreateJokeNode()
    create_fact_node = CreateFactNode()

    # Define the graph structure
    return Graph(
      source=create_joke_node,
      sink=create_fact_node,
      edges=[
          Edge(tail=create_joke_node, head=create_fact_node),
      ]
    )
