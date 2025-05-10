import random

from junjo.node import Node

from app.workflows.create_contact.store import CreateContactStore


class SelectAgeNode(Node[CreateContactStore]):
    """
    Node for selecting the age of a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to select the age of a contact.
        """

        # Determine age
        age = random.randint(18, 99)

        # Update state
        await store.set_age(age)


