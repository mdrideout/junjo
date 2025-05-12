from junjo import Edge, Graph

from base.sample_workflow.nodes.count_items_node.node import CountItemsNode
from base.sample_workflow.nodes.final_node.node import FinalNode

# Instantiate Nodes
count_items_node = CountItemsNode()
final_node = FinalNode()

sample_workflow_graph = Graph(
  source=count_items_node,
  sink=final_node,
  edges=[
      Edge(tail=count_items_node, head=final_node),
  ]
)
