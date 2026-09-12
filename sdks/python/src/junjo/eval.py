"""Faithful one-Node execution for application-owned live evaluations."""

from dataclasses import dataclass
from typing import Generic

from .correlation import ExecutionCorrelation
from .graph import Graph
from .node import Node
from .store import BaseStore, StateT
from .workflow import Workflow


@dataclass(frozen=True, slots=True)
class NodeEvaluationResult(Generic[StateT]):
    """Detached result of one Node executed through Junjo's normal lifecycle.

    :param run_id: Runtime ID of the generated one-Node evaluation Workflow.
    :param node_definition_id: Definition ID of the evaluated Node instance.
    :param state: Detached state snapshot after successful execution.
    """

    run_id: str
    node_definition_id: str
    state: StateT


async def evaluate_node(
    *,
    node: Node,
    store: BaseStore[StateT],
    correlation: ExecutionCorrelation | None = None,
) -> NodeEvaluationResult[StateT]:
    """Execute one real Node with production Node and Store lifecycle evidence.

    This helper is a one-shot envelope for live application evals. Construct a
    fresh ``node`` and initialized ``store`` for every case. Junjo executes them
    inside a generated single-Node Workflow so tracing, state transitions,
    lifecycle dispatch, cancellation, failures, and execution correlation use
    the same public runtime as production Workflows.

    This low-level helper executes a Node; it does not select dataset cases or
    judge their outputs. For repeatable experiments recorded in Junjo AI Studio,
    register a :class:`~junjo.evaluation.NodeTarget` in an
    :class:`~junjo.evaluation.EvaluationHarness`. Your application runs the
    targets and evaluators while Studio stores the datasets, outcomes, and
    linked execution evidence. Workflow and Agent targets use their respective
    :class:`~junjo.evaluation.WorkflowTarget` and
    :class:`~junjo.evaluation.AgentTarget` wrappers. Direct ``execute()`` calls
    remain appropriate for lower-level application tests.

    :param node: Fresh Node instance to evaluate.
    :param store: Fresh initialized Store containing the eval case input.
    :param correlation: Optional trusted application identity for this eval run.
    :returns: Detached final state and exact execution identities.
    """

    workflow = Workflow(
        name=f"Evaluate {node.name}",
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: store,
        max_iterations=1,
    )
    result = await workflow.execute(correlation=correlation)
    return NodeEvaluationResult(
        run_id=result.run_id,
        node_definition_id=node.id,
        state=result.state,
    )
