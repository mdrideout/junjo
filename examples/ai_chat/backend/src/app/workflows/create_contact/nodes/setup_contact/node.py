from junjo.node import Node

from app.db.models.contact.schemas import ContactCreate
from app.db.queries.create_setup_contact.repository import CreateSetupContactRepository
from app.workflows.create_contact.store import CreateContactStore


class SetupContactNode(Node[CreateContactStore]):
    async def service(self, store: CreateContactStore) -> None:
        """Sets up the contact and a conversation with them in the database."""

        # Get the current state
        state = await store.get_state()

                # 1) Null‐check all required top‐level fields
        if state.avatar_id is None:
            raise ValueError("avatar_id is required")
        if state.sex is None:
            raise ValueError("sex is required")
        if state.first_name is None:
            raise ValueError("first_name is required")
        if state.last_name is None:
            raise ValueError("last_name is required")
        if state.age is None:
            raise ValueError("age is required")
        if state.bio is None:
            raise ValueError("bio is required")

        # 2) Null‐check location info
        if state.loc_lat is None:
            raise ValueError("loc_lat is required")
        if state.loc_lon is None:
            raise ValueError("loc_lon is required")
        if state.location is None:
            raise ValueError("location (city/state) is required")

        # 3) Null‐check personality traits
        if state.personality_traits is None:
            raise ValueError("personality_traits is required")

        # 4) Build the ContactCreate by flattening nested state
        contact_create = ContactCreate(
            avatar_id=state.avatar_id,
            sex=state.sex,
            first_name=state.first_name,
            last_name=state.last_name,
            age=state.age,
            openness=state.personality_traits.openness,
            conscientiousness=state.personality_traits.conscientiousness,
            neuroticism=state.personality_traits.neuroticism,
            agreeableness=state.personality_traits.agreeableness,
            extraversion=state.personality_traits.extraversion,
            intelligence=state.personality_traits.intelligence,
            religiousness=state.personality_traits.religiousness,
            attractiveness=state.personality_traits.attractiveness,
            trauma=state.personality_traits.trauma,
            latitude=state.loc_lat,
            longitude=state.loc_lon,
            city=state.location.city,
            state=state.location.state,
            bio=state.bio,
        )

        # Save the contact to the database
        setup_contact_result = await CreateSetupContactRepository.create_setup_contact(contact_create)

        # Update the state with the saved contact
        await store.set_final_contact(setup_contact_result)
