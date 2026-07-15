"""Private state and explicit actions for contact creation."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ContactSex, ConversationOverview, ImageArtifact, PersonalityTraits


class ContactWorkflowState(BaseState):
    contact_id: str
    conversation_id: str
    sex: ContactSex
    age: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    state: str | None = None
    personality: PersonalityTraits | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    avatar: ImageArtifact | None = None
    result: ConversationOverview | None = None


class ContactWorkflowStore(BaseStore[ContactWorkflowState]):
    async def set_age(self, age: int) -> None:
        await self.set_state({"age": age})

    async def set_location(
        self,
        *,
        latitude: float,
        longitude: float,
        city: str,
        state: str,
    ) -> None:
        await self.set_state(
            {
                "latitude": latitude,
                "longitude": longitude,
                "city": city,
                "state": state,
            }
        )

    async def set_personality(self, personality: PersonalityTraits) -> None:
        await self.set_state({"personality": personality})

    async def set_bio(self, bio: str) -> None:
        await self.set_state({"bio": bio})

    async def set_name(self, *, first_name: str, last_name: str) -> None:
        await self.set_state({"first_name": first_name, "last_name": last_name})

    async def set_avatar(self, avatar: ImageArtifact) -> None:
        await self.set_state({"avatar": avatar})

    async def set_result(self, result: ConversationOverview) -> None:
        await self.set_state({"result": result})
