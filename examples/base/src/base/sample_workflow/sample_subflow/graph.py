from junjo import Edge, Graph

from base.sample_workflow.sample_subflow.nodes.create_fact_node.node import CreateFactNode
from base.sample_workflow.sample_subflow.nodes.create_joke_node.node import CreateJokeNode

# Instantiate the nodes
create_joke_node = CreateJokeNode()
create_fact_node = CreateFactNode()

# Define the graph structure
sample_subflow_graph = Graph(
  source=create_joke_node,
  sink=create_fact_node,
  edges=[
      Edge(tail=create_joke_node, head=create_fact_node),
  ]
)
