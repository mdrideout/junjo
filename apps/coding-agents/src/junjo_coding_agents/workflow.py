"""The example's real Junjo graph; the host supplies all reasoning results."""

from typing import Protocol

from junjo import BaseState, BaseStore, Condition, Edge, Graph, Node, Workflow
from pydantic import BaseModel, ConfigDict, StrictBool


class Findings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    has_bug: StrictBool
    explanation: str


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str


class ReviewState(BaseState):
    code: str
    requirement: str = "Return True exactly when the integer n is even."
    findings: Findings | None = None
    explanation: str | None = None


class ReviewStore(BaseStore[ReviewState]):
    async def record_findings(self, findings: Findings) -> None:
        await self.set_state({"findings": findings})

    async def record_explanation(self, explanation: str) -> None:
        await self.set_state({"explanation": explanation})


class Worker(Protocol):
    async def request(self, instructions: str, state: ReviewState, output_type: type[BaseModel]) -> BaseModel: ...


class InspectFunction(Node[ReviewStore]):
    def __init__(self, worker: Worker):
        super().__init__()
        self.worker = worker

    async def service(self, store: ReviewStore) -> None:
        result = await self.worker.request(
            "Inspect the function against its requirement. Return whether it has a bug and explain your evidence.",
            await store.get_state(),
            Findings,
        )
        await store.record_findings(Findings.model_validate(result))


class ExplainCorrection(Node[ReviewStore]):
    def __init__(self, worker: Worker):
        super().__init__()
        self.worker = worker

    async def service(self, store: ReviewStore) -> None:
        result = await self.worker.request(
            "Explain the smallest correction and give one input demonstrating the original bug. Do not edit files.",
            await store.get_state(),
            Explanation,
        )
        await store.record_explanation(Explanation.model_validate(result).explanation)


class ExplainCorrectness(Node[ReviewStore]):
    def __init__(self, worker: Worker):
        super().__init__()
        self.worker = worker

    async def service(self, store: ReviewStore) -> None:
        result = await self.worker.request(
            "Explain why the function satisfies its requirement, with an even and an odd example.",
            await store.get_state(),
            Explanation,
        )
        await store.record_explanation(Explanation.model_validate(result).explanation)


class BugFound(Condition[ReviewState]):
    def evaluate(self, state: ReviewState) -> bool:
        assert state.findings is not None
        return state.findings.has_bug


FIXTURES = {
    "buggy": "def is_even(n: int) -> bool:\n    return n % 2 == 1\n",
    "correct": "def is_even(n: int) -> bool:\n    return n % 2 == 0\n",
}


def build_review(worker: Worker, fixture: str) -> Workflow[ReviewState, ReviewStore]:
    code = FIXTURES[fixture]

    def graph() -> Graph:
        inspect = InspectFunction(worker)
        correction = ExplainCorrection(worker)
        correctness = ExplainCorrectness(worker)
        return Graph(
            source=inspect,
            sinks=[correction, correctness],
            edges=[
                Edge(tail=inspect, head=correction, condition=BugFound()),
                Edge(tail=inspect, head=correctness),
            ],
        )

    return Workflow(
        name="FunctionReview",
        graph_factory=graph,
        store_factory=lambda: ReviewStore(initial_state=ReviewState(code=code)),
    )
