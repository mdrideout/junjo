from junjo import Edge, Graph, RunConcurrent

from base.sample_workflow.conditions import CounterIsEven, MatchesCount
from base.sample_workflow.nodes.add_ten_node.node import AddTenNode
from base.sample_workflow.nodes.count_items_node.node import CountItemsNode
from base.sample_workflow.nodes.decrement_node.node import DecrementNode
from base.sample_workflow.nodes.even_path_node.node import EvenPathNode
from base.sample_workflow.nodes.exact_path_node.node import ExactPathNode
from base.sample_workflow.nodes.final_node.node import FinalNode
from base.sample_workflow.nodes.increment_node.node import IncrementNode
from base.sample_workflow.nodes.odd_path_node.node import OddPathNode
from base.sample_workflow.sample_subflow.graph import sample_subflow_graph
from base.sample_workflow.sample_subflow.store import SampleSubflowState, SampleSubflowStore
from base.sample_workflow.sample_subflow.subflow import SampleSubflow

# Instantiate Nodes
count_items_node = CountItemsNode()
even_path_node = EvenPathNode()
odd_path_node = OddPathNode()
exact_path_node = ExactPathNode()
final_node = FinalNode()

# Concurrency Runner Example
increment_node = IncrementNode()
decrement_node = DecrementNode()
add_ten_node = AddTenNode()
modify_counter_concurrent = RunConcurrent(
    name="Counter Nodes",
    items=[increment_node, decrement_node, add_ten_node],
)

# Instantiate the subflow
sample_subflow = SampleSubflow(
    graph=sample_subflow_graph,
    store=SampleSubflowStore(initial_state=SampleSubflowState())
)

sample_workflow_graph = Graph(
  source=count_items_node,
  sink=final_node,
  edges=[
      Edge(tail=count_items_node, head=modify_counter_concurrent),
      Edge(tail=modify_counter_concurrent, head=sample_subflow),

      # Subflow -> transitions
      # Conditions are evaluated in order, the first edge with a true condition is taken
      Edge(tail=sample_subflow, head=exact_path_node, condition=MatchesCount(15)),
      Edge(tail=sample_subflow, head=even_path_node, condition=CounterIsEven()),
      Edge(tail=sample_subflow, head=odd_path_node), # Default / fallback / only logical option

      # -> Final Node transitions
      Edge(tail=exact_path_node, head=final_node),
      Edge(tail=even_path_node, head=final_node),
      Edge(tail=odd_path_node, head=final_node),
  ]
)
