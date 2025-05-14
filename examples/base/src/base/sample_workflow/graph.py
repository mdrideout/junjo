from junjo import Edge, Graph

from base.sample_workflow.nodes.count_items_node.node import CountItemsNode
from base.sample_workflow.nodes.final_node.node import FinalNode
from base.sample_workflow.sample_subflow.graph import sample_subflow_graph
from base.sample_workflow.sample_subflow.store import SampleSubflowState, SampleSubflowStore
from base.sample_workflow.sample_subflow.subflow import SampleSubflow

# Instantiate Nodes
count_items_node = CountItemsNode()
final_node = FinalNode()

# Instantiate the subflow
sample_subflow = SampleSubflow(
    graph=sample_subflow_graph,
    store=SampleSubflowStore(initial_state=SampleSubflowState())
)

sample_workflow_graph = Graph(
  source=count_items_node,
  sink=final_node,
  edges=[
      Edge(tail=count_items_node, head=sample_subflow),
      Edge(tail=sample_subflow, head=final_node),
  ]
)
