"""Isolated state owned by the avatar-generation Subflow."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ContactSex, ImageArtifact, PersonalityTraits


class AvatarWorkflowState(BaseState):
    personality: PersonalityTraits | None = None
    bio: str | None = None
    city: str | None = None
    state: str | None = None
    sex: ContactSex | None = None
    age: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    inspiration: str | None = None
    artifact: ImageArtifact | None = None


class AvatarWorkflowStore(BaseStore[AvatarWorkflowState]):
    async def set_inspiration(self, inspiration: str) -> None:
        await self.set_state({"inspiration": inspiration})

    async def set_artifact(self, artifact: ImageArtifact) -> None:
        await self.set_state({"artifact": artifact})
