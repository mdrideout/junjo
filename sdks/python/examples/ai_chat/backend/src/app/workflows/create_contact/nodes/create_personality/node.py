from junjo.node import Node

from app.workflows.create_contact.schemas import PersonalityTraits
from app.workflows.create_contact.store import CreateContactStore


class CreatePersonalityNode(Node[CreateContactStore]):
    """
    Node for creating a personality for a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to create a personality for a contact.
        """

        # Determine sex
        personality = PersonalityTraits.generate_random()

        # Update state
        await store.set_personality_traits(personality)


