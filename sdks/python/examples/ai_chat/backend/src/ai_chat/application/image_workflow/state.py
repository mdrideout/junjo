"""Private state and actions for one image Workflow execution."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ImageArtifact


class ImageWorkflowState(BaseState):
    prompt: str
    prepared_prompt: str | None = None
    alt_text: str | None = None
    artifact: ImageArtifact | None = None


class ImageWorkflowStore(BaseStore[ImageWorkflowState]):
    async def set_prepared_prompt(self, *, prompt: str, alt_text: str) -> None:
        await self.set_state({"prepared_prompt": prompt, "alt_text": alt_text})

    async def set_artifact(self, artifact: ImageArtifact) -> None:
        await self.set_state({"artifact": artifact})
