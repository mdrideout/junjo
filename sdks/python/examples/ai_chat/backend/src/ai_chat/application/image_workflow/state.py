"""Private state for the shared avatar-conditioned image-response Workflow."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ChatAgentOutput, CompletedTurn, ContactProfile


class ImageWorkflowState(BaseState):
    request: str = ""
    contact: ContactProfile | None = None
    recent_turns: tuple[CompletedTurn, ...] = ()
    inspiration: str | None = None
    output: ChatAgentOutput | None = None


class ImageWorkflowStore(BaseStore[ImageWorkflowState]):
    async def set_inspiration(self, inspiration: str) -> None:
        await self.set_state({"inspiration": inspiration})

    async def set_output(self, output: ChatAgentOutput) -> None:
        await self.set_state({"output": output})
