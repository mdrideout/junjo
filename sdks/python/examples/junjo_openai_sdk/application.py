"""Order support state and Tools; provider calls and telemetry live elsewhere."""

from datetime import date

from pydantic import BaseModel, ConfigDict

from junjo import Agent, BaseState, BaseStore, Condition, Edge, Graph, ModelDriverBinding, Node, Tool, Workflow
from junjo.agent import AgentRunContext

# A fixed date keeps the fictional policy decisions reproducible on every run.
DEMO_AS_OF = date(2026, 9, 20)


class OrderFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    item: str
    delivered_on: date


SAMPLE_ORDERS = {
    "ORD-1001": OrderFacts(order_id="ORD-1001", item="Desk lamp", delivered_on=date(2026, 9, 10)),
    "ORD-1002": OrderFacts(order_id="ORD-1002", item="Travel mug", delivered_on=date(2026, 8, 1)),
}


class OrderSupportState(BaseState):
    as_of: date = DEMO_AS_OF
    return_window_days: int = 30
    order: OrderFacts | None = None
    days_since_delivery: int | None = None
    within_return_window: bool | None = None
    eligible: bool | None = None
    decision_reason: str | None = None


class OrderSupportStore(BaseStore[OrderSupportState]):
    async def record_order(self, order: OrderFacts) -> None:
        # A new lookup clears any decision about a previously loaded order.
        await self.set_state(
            {
                "order": order,
                "days_since_delivery": None,
                "within_return_window": None,
                "eligible": None,
                "decision_reason": None,
            }
        )

    async def record_policy_evaluation(self, days_since_delivery: int, within_return_window: bool) -> None:
        await self.set_state(
            {
                "days_since_delivery": days_since_delivery,
                "within_return_window": within_return_window,
                "eligible": None,
                "decision_reason": None,
            }
        )

    async def record_decision(self, eligible: bool, reason: str) -> None:
        await self.set_state({"eligible": eligible, "decision_reason": reason})


class SupportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    question: str


class SupportAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    eligible: bool
    explanation: str


class LookupOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str


class LookupOrderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: OrderFacts
    as_of: date
    return_window_days: int


class EligibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EligibilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    eligible: bool
    decision_reason: str


class LookupOrderNode(Node[OrderSupportStore]):
    def __init__(self, order_id: str) -> None:
        super().__init__()
        self.order_id = order_id

    async def service(self, store: OrderSupportStore) -> None:
        await store.record_order(SAMPLE_ORDERS[self.order_id])


class EvaluateReturnPolicyNode(Node[OrderSupportStore]):
    async def service(self, store: OrderSupportStore) -> None:
        state = await store.get_state()
        if state.order is None:
            raise ValueError("Look up an order before checking return eligibility.")
        days_since_delivery = (state.as_of - state.order.delivered_on).days
        await store.record_policy_evaluation(
            days_since_delivery, within_return_window=0 <= days_since_delivery <= state.return_window_days
        )


class EligibleReturnNode(Node[OrderSupportStore]):
    async def service(self, store: OrderSupportStore) -> None:
        state = await store.get_state()
        await store.record_decision(
            True,
            f"Delivered {state.days_since_delivery} days ago; within the {state.return_window_days}-day return window.",
        )


class IneligibleReturnNode(Node[OrderSupportStore]):
    async def service(self, store: OrderSupportStore) -> None:
        state = await store.get_state()
        await store.record_decision(
            False,
            f"Delivered {state.days_since_delivery} days ago; "
            f"outside the {state.return_window_days}-day return window.",
        )


class WithinReturnWindow(Condition[OrderSupportState]):
    def evaluate(self, state: OrderSupportState) -> bool:
        return state.within_return_window is True


def return_eligibility_graph() -> Graph:
    evaluate, eligible, ineligible = EvaluateReturnPolicyNode(), EligibleReturnNode(), IneligibleReturnNode()
    return Graph(
        source=evaluate,
        sinks=[eligible, ineligible],
        edges=[
            Edge(tail=evaluate, head=eligible, condition=WithinReturnWindow()),
            Edge(tail=evaluate, head=ineligible),  # fallback when the policy check is false
        ],
    )


return_eligibility_workflow = Workflow[OrderSupportState, OrderSupportStore](
    name="ReturnEligibilityWorkflow",
    graph_factory=return_eligibility_graph,
    store_factory=lambda: OrderSupportStore(OrderSupportState()),
)


def eligibility_result(state: OrderSupportState) -> EligibilityResult:
    # Explicitly select the application facts the model should see.
    if state.order is None or state.eligible is None or state.decision_reason is None:
        raise ValueError("Return eligibility has not been decided.")
    return EligibilityResult(
        order_id=state.order.order_id, eligible=state.eligible, decision_reason=state.decision_reason
    )


async def lookup_order(input: LookupOrderInput, context: AgentRunContext[None, OrderSupportStore]) -> LookupOrderResult:
    # Execute the Node through its public lifecycle, using the Agent's application Store.
    await LookupOrderNode(input.order_id).execute(context.store, context.definition_id)
    state = await context.store.get_state()
    assert state.order is not None
    return LookupOrderResult(order=state.order, as_of=state.as_of, return_window_days=state.return_window_days)


async def check_return_eligibility(
    input: EligibilityInput, context: AgentRunContext[None, OrderSupportStore]
) -> EligibilityResult:
    result = await return_eligibility_workflow.execute(store=context.store)
    return eligibility_result(result.state)


def build_agent(
    model: ModelDriverBinding,
) -> Agent[SupportRequest, SupportAnswer, None, OrderSupportState, OrderSupportStore]:
    return Agent(
        key="order-support",
        name="Order support",
        instructions=(
            "Answer the customer's return question for the requested order. First call lookup_order with their "
            "order_id, then call check_return_eligibility for the loaded order. Use that Tool's eligibility and "
            "decision reason in your final answer. Do not invent order facts or override the policy decision. "
            "This is a fictional store policy example; checking eligibility does not initiate a return or refund."
        ),
        input_type=SupportRequest,
        output_type=SupportAnswer,
        model=model,
        store_factory=lambda: OrderSupportStore(OrderSupportState()),
        tools=[
            Tool[LookupOrderInput, LookupOrderResult, None, OrderSupportStore](
                name="lookup_order",
                description="Look up a sample order by order_id and record its facts in application state.",
                input_type=LookupOrderInput,
                output_type=LookupOrderResult,
                shared_service=lookup_order,
            ),
            Tool[EligibilityInput, EligibilityResult, None, OrderSupportStore](
                name="check_return_eligibility",
                description="After lookup_order, run the conditional return policy Workflow for the loaded order.",
                input_type=EligibilityInput,
                output_type=EligibilityResult,
                shared_service=check_return_eligibility,
            ),
        ],
    )
