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

        min_age, max_age = 18, 65

        # use Beta(α,β) for skew
        alpha, beta = 2.0, 9.0
        fraction = random.betavariate(alpha, beta)
        age = int(min_age + (max_age - min_age) * fraction)

        # Update state
        await store.set_age(age)


