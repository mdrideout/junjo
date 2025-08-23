

from junjo import Workflow
from junjo.telemetry.hook_manager import HookManager

from base.sample_workflow.graph import create_sample_workflow_graph
from base.sample_workflow.store import SampleWorkflowState, SampleWorkflowStore

# Initialize a store
initial_state = SampleWorkflowState(items=["laser", "coffee", "horse"], counter=0)
sample_workflow_store = SampleWorkflowStore(initial_state=initial_state)

# Create the workflow
sample_workflow = Workflow[SampleWorkflowState, SampleWorkflowStore](
    name="demo_base_workflow",
    graph_factory=create_sample_workflow_graph,
    store_factory=lambda: SampleWorkflowStore(
        initial_state=SampleWorkflowState(
            items=["laser", "coffee", "horse"],
            counter=0,
        )
    ),
    hook_manager=HookManager(verbose_logging=False, open_telemetry=True),
)



