from __future__ import annotations

from typing import TYPE_CHECKING

from junjo import Workflow

from base.sample_workflow.graph import create_sample_workflow_graph
from base.sample_workflow.store import SampleWorkflowState, SampleWorkflowStore

if TYPE_CHECKING:
    from junjo import Hooks


def create_sample_workflow(
    hooks: Hooks | None = None,
) -> Workflow[SampleWorkflowState, SampleWorkflowStore]:
    """
    Build the base example workflow.

    The workflow definition remains focused on graph and store construction.
    Hook registration for logging or external observation should live in a
    separate module or entrypoint so the workflow definition stays easy to
    understand in isolation.
    """
    return Workflow[SampleWorkflowState, SampleWorkflowStore](
        name="demo_base_workflow",
        graph_factory=create_sample_workflow_graph,
        store_factory=lambda: SampleWorkflowStore(
            initial_state=SampleWorkflowState(
                items=["laser", "coffee", "horse"],
                counter=0,
            )
        ),
        hooks=hooks,
    )


sample_workflow = create_sample_workflow()
