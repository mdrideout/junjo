"""Single-responsibility Nodes for the model-powered contact Workflow."""

import random

from junjo import Node
from pydantic import BaseModel, Field

from ai_chat.domain.models import ContactProfile, Conversation, PersonalityTraits
from ai_chat.domain.ports import ContactWriter, LanguageModel

from .geography import random_us_coordinates
from .prompts import biography_prompt, location_prompt, name_prompt
from .state import ContactWorkflowStore


class LocationResult(BaseModel):
    city: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)


class NameResult(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)


class SelectAgeNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        fraction = random.betavariate(1.7, 9.0)
        await store.set_age(int(18 + (65 - 18) * fraction))


class SelectLocationNode(Node[ContactWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: ContactWorkflowStore) -> None:
        latitude, longitude = random_us_coordinates()
        location = await self._language.generate_structured(
            prompt=location_prompt(latitude, longitude),
            output_type=LocationResult,
        )
        await store.set_location(
            latitude=latitude,
            longitude=longitude,
            city=location.city,
            state=location.state.upper(),
        )


class CreatePersonalityNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        personality = PersonalityTraits(
            openness=round(random.betavariate(5, 2), 2),
            conscientiousness=round(random.uniform(0, 1), 2),
            extraversion=round(random.betavariate(5, 2), 2),
            agreeableness=round(random.betavariate(5, 2), 2),
            neuroticism=round(random.uniform(0, 1), 2),
            intelligence=round(random.uniform(0, 1), 2),
            religiousness=round(random.betavariate(2, 5), 2),
            attractiveness=round(random.betavariate(9, 2), 2),
            trauma=round(random.betavariate(2, 5), 2),
        )
        await store.set_personality(personality)


class CreateBioNode(Node[ContactWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        if state.personality is None or state.city is None or state.state is None or state.age is None:
            raise RuntimeError("Initial contact facts must exist before biography creation.")
        bio = await self._language.generate_text(
            prompt=biography_prompt(
                personality=state.personality,
                city=state.city,
                state=state.state,
                age=state.age,
                sex=state.sex,
            )
        )
        await store.set_bio(bio)


class CreateNameNode(Node[ContactWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        if state.personality is None or state.city is None or state.state is None or state.age is None:
            raise RuntimeError("Initial contact facts must exist before name creation.")
        name = await self._language.generate_structured(
            prompt=name_prompt(
                personality=state.personality,
                city=state.city,
                state=state.state,
                age=state.age,
                sex=state.sex,
            ),
            output_type=NameResult,
        )
        await store.set_name(first_name=name.first_name, last_name=name.last_name)


class PersistContactNode(Node[ContactWorkflowStore]):
    def __init__(self, contacts: ContactWriter) -> None:
        super().__init__()
        self._contacts = contacts

    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        required = (
            state.age,
            state.latitude,
            state.longitude,
            state.city,
            state.state,
            state.personality,
            state.first_name,
            state.last_name,
            state.bio,
            state.avatar,
        )
        if any(value is None for value in required):
            raise RuntimeError("Contact is incomplete and cannot be persisted.")
        assert state.age is not None
        assert state.latitude is not None
        assert state.longitude is not None
        assert state.city is not None
        assert state.state is not None
        assert state.personality is not None
        assert state.first_name is not None
        assert state.last_name is not None
        assert state.bio is not None
        assert state.avatar is not None
        contact = ContactProfile(
            id=state.contact_id,
            first_name=state.first_name,
            last_name=state.last_name,
            sex=state.sex,
            age=state.age,
            personality=state.personality,
            latitude=state.latitude,
            longitude=state.longitude,
            city=state.city,
            state=state.state,
            bio=state.bio,
            avatar=state.avatar,
        )
        conversation = Conversation(
            id=state.conversation_id,
            title=contact.display_name,
            contact_id=contact.id,
        )
        await store.set_result(await self._contacts.create_contact(contact=contact, conversation=conversation))
