from dotenv import load_dotenv

from base.otel_config import init_otel
from base.sample_workflow.store import SampleWorkflowState
from base.sample_workflow.workflow import sample_workflow, sample_workflow_store


async def main():
    """The main entry point for the application."""

    # Load the environment variables
    load_dotenv()

    # Setup OpenTelemetry before anything else happens
    exporter = init_otel(service_name="Junjo Base Example")

    # Subscribe to state changes
    def on_state_change(new_state: SampleWorkflowState):
        print("State changed:", new_state.model_dump())
    unsubscribe = await sample_workflow_store.subscribe(on_state_change)

    print("Executing the workflow...")
    await sample_workflow.execute()
    print("Final state: ", await sample_workflow.get_state_json())

    # Cleanup
    await unsubscribe()

    print("Done executing the base example workflow.")

    # Flush telemetry before exit
    if exporter is not None:
        print("Flushing telemetry...")
        exporter.flush()
    return

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
