from junjo.node import Node

from app.workflows.create_contact.nodes.select_location.services.get_nearest_city_state import get_nearest_city_state
from app.workflows.create_contact.nodes.select_location.services.random_us_latlon import random_us_latlon
from app.workflows.create_contact.store import CreateContactStore


class SelectLocationNode(Node[CreateContactStore]):
    """
    Node for selecting the location of a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to select the location of a contact.
        """

        # Get the random us lat / long
        [lat, long] = random_us_latlon()

        # Fetch the nearest city and state using an LLM call
        loc_city_state = await get_nearest_city_state(lat, long)

        # Update state
        await store.set_loc_lat(lat)
        await store.set_loc_lon(long)
        await store.set_location(loc_city_state)


