"""Run the same application with a factory-owned or borrowed Store."""

import argparse
import asyncio
import os

from application import OrderSupportState, OrderSupportStore, SupportRequest, build_agent
from driver import OpenAIModelDriver
from openai import AsyncOpenAI
from opentelemetry import trace
from telemetry import init_telemetry

from junjo import ModelDriverBinding, ModelDriverDescriptor


async def run(args: argparse.Namespace) -> None:
    required = ("OPENAI_MODEL", "OPENAI_API_KEY", "JUNJO_AI_STUDIO_API_KEY", "JUNJO_OTLP_ENDPOINT", "JUNJO_STUDIO_URL")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))
    model_name = os.environ["OPENAI_MODEL"]
    provider = init_telemetry()
    try:
        async with AsyncOpenAI() as client:
            binding = ModelDriverBinding.per_run(
                descriptor=ModelDriverDescriptor(driver_key="openai-responses", provider="openai", model=model_name),
                factory=lambda: OpenAIModelDriver(client, model_name),
            )
            agent = build_agent(binding)
            store = OrderSupportStore(OrderSupportState()) if args.store == "borrowed" else None
            with trace.get_tracer(__name__).start_as_current_span("Answer return question") as span:
                result = await agent.execute(
                    SupportRequest(order_id=args.order_id, question=args.question), dependencies=None, store=store
                )
                assert result.application_state is not None
                print("Answer:", result.output.model_dump_json(indent=2))
                print("Application state:", result.application_state.model_dump_json(indent=2))
                print("Trace ID:", format(span.get_span_context().trace_id, "032x"))
                print("Studio:", os.environ["JUNJO_STUDIO_URL"])
    finally:
        provider.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Answer a sample order-return question with observable application state."
    )
    parser.add_argument("order_id", nargs="?", default="ORD-1001", help="Sample order: ORD-1001 or ORD-1002")
    parser.add_argument("--question", default="Can I return this order? Please explain the decision.")
    parser.add_argument(
        "--store",
        choices=["owned", "borrowed"],
        default="owned",
        help="Create the Store in the Agent factory or caller",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
