from dotenv import load_dotenv

from base.otel_config import init_otel
from base.sample_workflow.workflow import sample_workflow


async def main():
    """The main entry point for the application."""

    # Load the environment variables
    load_dotenv()

    # Setup OpenTelemetry before anything else happens
    exporter = init_otel(service_name="Junjo Base Example")

    print("Executing the workflow...")
    result = await sample_workflow.execute()
    print("Final state: ", result.state.model_dump_json())

    print("Done executing the base example workflow.")

    # Flush telemetry before exit
    if exporter is not None:
        print("Flushing telemetry...")
        exporter.flush()
    return

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
