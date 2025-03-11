import asyncio

from junjo.node import Node

from app.db.models.message.services import MessageService
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class SaveMessageNode(Node[MessageWorkflowStore]):
    """Save the message to the database and append it to state."""

    async def service(self, store: MessageWorkflowStore) -> None:
        state = store.get_state()

        # Save the received message to the database
        print("INSERTING THE MESSAGE TO THE DATABASE.")
        saved_message = await MessageService.save_message(state.received_message)
        print(f"Message inserted: {saved_message}")

        # Append the saved message to state
        store.append_conversation_history(saved_message)

        # Create a 1 second artificial delay
        await asyncio.sleep(1)


        return
