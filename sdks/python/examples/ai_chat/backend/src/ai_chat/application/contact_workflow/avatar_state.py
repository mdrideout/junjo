"""Isolated state owned by the avatar-generation Subflow."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ImageArtifact


class AvatarWorkflowState(BaseState):
    prompt: str = ""
    alt_text: str = ""
    artifact: ImageArtifact | None = None


class AvatarWorkflowStore(BaseStore[AvatarWorkflowState]):
    async def set_request(self, *, prompt: str, alt_text: str) -> None:
        await self.set_state({"prompt": prompt, "alt_text": alt_text})

    async def set_artifact(self, artifact: ImageArtifact) -> None:
        await self.set_state({"artifact": artifact})
