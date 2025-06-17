from junjo import Edge, Graph

from run_for_every.sample_workflow.nodes.final_node.node import FinalNode
from run_for_every.sample_workflow.nodes.start_node.node import StartNode

# Instantiate Nodes
start_node = StartNode()
final_node = FinalNode()

sample_workflow_graph = Graph(
  source=start_node,
  sink=final_node,
  edges=[
      Edge(tail=start_node, head=final_node),
  ]
)
