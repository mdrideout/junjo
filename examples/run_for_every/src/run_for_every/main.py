from dotenv import load_dotenv

from run_for_every.otel_config import init_otel
from run_for_every.sample_workflow.workflow import sample_workflow


async def main():
    """The main entry point for the application."""

    # Load the environment variables
    load_dotenv()

    # Setup OpenTelemetry before anything else happens
    init_otel(service_name="Junjo Base Example")

    # TODO: Make the subscriber something that is passed to execute()
    # # Subscribe to state changes
    # def on_state_change(new_state: SampleWorkflowState):
    #     print("State changed:", new_state.model_dump())

    # store = sample_workflow.store
    # unsubscribe = await store.subscribe(on_state_change)

    print("Executing the workflow...")
    await sample_workflow.execute()
    print("Final state: ", await sample_workflow.get_state_json())

    # # Cleanup
    # await unsubscribe()

    print("Done executing the base example workflow.")
    return

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
