from junjo.node import Node

from app.workflows.create_contact.store import CreateContactStore


class CreateContactSinkNode(Node[CreateContactStore]):
    async def service(self, store: CreateContactStore) -> None:
        print("Running sink node.")
        pass
