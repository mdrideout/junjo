import logging

from dotenv import load_dotenv

from base.otel_config import init_otel
from base.sample_workflow.hooks import create_logging_hooks
from base.sample_workflow.workflow import create_sample_workflow

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure application logging for the base example."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("junjo").setLevel(logging.DEBUG)


async def main():
    """The main entry point for the application."""

    # Load the environment variables
    load_dotenv()
    configure_logging()

    # Setup OpenTelemetry before anything else happens
    tracer_provider = init_otel(service_name="Junjo Base Example")

    try:
        workflow = create_sample_workflow(hooks=create_logging_hooks())

        logger.info("Executing the workflow...")
        result = await workflow.execute()
        logger.info("Final state: %s", result.state.model_dump_json())

        logger.info("Done executing the base example workflow.")
    finally:
        if tracer_provider is not None:
            logger.info("Shutting down the OpenTelemetry tracer provider...")
            tracer_provider.shutdown()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
