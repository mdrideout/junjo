"""Private state and explicit actions for contact creation."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ContactSex, ConversationOverview, ImageArtifact


class ContactWorkflowState(BaseState):
    contact_id: str
    conversation_id: str
    sex: ContactSex
    age: int | None = None
    city: str | None = None
    state: str | None = None
    personality: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    avatar: ImageArtifact | None = None
    result: ConversationOverview | None = None


class ContactWorkflowStore(BaseStore[ContactWorkflowState]):
    async def set_age(self, age: int) -> None:
        await self.set_state({"age": age})

    async def set_location(self, *, city: str, state: str) -> None:
        await self.set_state({"city": city, "state": state})

    async def set_personality(self, personality: str) -> None:
        await self.set_state({"personality": personality})

    async def set_identity(
        self,
        *,
        first_name: str,
        last_name: str,
        bio: str,
    ) -> None:
        await self.set_state({"first_name": first_name, "last_name": last_name, "bio": bio})

    async def set_avatar(self, avatar: ImageArtifact) -> None:
        await self.set_state({"avatar": avatar})

    async def set_result(self, result: ConversationOverview) -> None:
        await self.set_state({"result": result})
