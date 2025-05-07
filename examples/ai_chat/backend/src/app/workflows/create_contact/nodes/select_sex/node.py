from junjo.node import Node

from app.workflows.create_contact.nodes.select_sex.service import select_sex
from app.workflows.create_contact.store import CreateContactStore


class SelectSexNode(Node[CreateContactStore]):
    """
    Node for selecting the sex of a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to select the sex of a contact.
        """

        # Determine sex
        sex = select_sex()

        # Update state
        await store.set_sex(sex)


