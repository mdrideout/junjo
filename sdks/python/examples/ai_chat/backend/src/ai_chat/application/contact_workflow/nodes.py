"""Deterministic Nodes for the observable contact creation proof."""

import hashlib

from junjo import Node

from ai_chat.domain.models import ContactProfile, ContactSex, Conversation
from ai_chat.domain.ports import ContactWriter

from .state import ContactWorkflowStore

_LOCATIONS = (
    ("Portland", "ME"),
    ("Brooklyn", "NY"),
    ("Chicago", "IL"),
    ("Austin", "TX"),
    ("Seattle", "WA"),
)
_PERSONALITIES = (
    "curious, warm, and always ready to try a new neighborhood spot",
    "thoughtful, playful, and happiest when making something by hand",
    "calm, adventurous, and interested in the stories behind everyday things",
)
_MALE_NAMES = ("Theo", "Elliot", "Miles", "Julian", "Noah")
_FEMALE_NAMES = ("Maya", "Nora", "Elena", "Claire", "Sofia")
_LAST_NAMES = ("Rivera", "Bennett", "Park", "Morgan", "Sullivan")


def _index(identity: str, salt: str, length: int) -> int:
    digest = hashlib.sha256(f"{identity}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4]) % length


class SelectAgeNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        await store.set_age(24 + _index(state.contact_id, "age", 28))


class SelectLocationNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        city, region = _LOCATIONS[_index(state.contact_id, "location", len(_LOCATIONS))]
        await store.set_location(city=city, state=region)


class SelectPersonalityNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        value = _PERSONALITIES[_index(state.contact_id, "personality", len(_PERSONALITIES))]
        await store.set_personality(value)


class CreateIdentityNode(Node[ContactWorkflowStore]):
    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        if state.age is None or state.city is None or state.personality is None:
            raise RuntimeError("Initial contact facts must be created first.")
        names = _MALE_NAMES if state.sex is ContactSex.MALE else _FEMALE_NAMES
        first_name = names[_index(state.contact_id, "first-name", len(names))]
        last_name = _LAST_NAMES[_index(state.contact_id, "last-name", len(_LAST_NAMES))]
        bio = (
            f"{first_name} is {state.personality}. They are based in "
            f"{state.city} and enjoy conversations that become practical plans."
        )
        await store.set_identity(
            first_name=first_name,
            last_name=last_name,
            bio=bio,
        )


class PersistContactNode(Node[ContactWorkflowStore]):
    def __init__(self, contacts: ContactWriter) -> None:
        super().__init__()
        self._contacts = contacts

    async def service(self, store: ContactWorkflowStore) -> None:
        state = await store.get_state()
        if None in (
            state.age,
            state.city,
            state.state,
            state.first_name,
            state.last_name,
            state.bio,
            state.avatar,
        ):
            raise RuntimeError("Contact is incomplete and cannot be persisted.")
        assert state.age is not None
        assert state.city is not None
        assert state.state is not None
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
        result = await self._contacts.create_contact(
            contact=contact,
            conversation=conversation,
        )
        await store.set_result(result)
