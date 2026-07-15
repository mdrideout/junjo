"""Known model-powered procedure for a persona-consistent image response."""

from junjo import Node

from ai_chat.domain.models import ChatAgentOutput
from ai_chat.domain.ports import ImageModel, LanguageModel

from .prompts import image_inspiration_prompt, image_message_prompt
from .state import ImageWorkflowStore


class CreateImageInspirationNode(Node[ImageWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: ImageWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None or not state.request.strip():
            raise RuntimeError("Image Workflow context is incomplete.")
        inspiration = await self._language.generate_text(
            prompt=image_inspiration_prompt(
                contact=state.contact,
                turns=state.recent_turns,
                current_message=state.request,
            )
        )
        await store.set_inspiration(inspiration)


class CreateImageResponseNode(Node[ImageWorkflowStore]):
    def __init__(self, *, language: LanguageModel, images: ImageModel) -> None:
        super().__init__()
        self._language = language
        self._images = images

    async def service(self, store: ImageWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None or state.inspiration is None:
            raise RuntimeError("Image inspiration must exist before image editing.")
        result = await self._images.edit(
            source=state.contact.avatar,
            prompt=state.inspiration,
            alt_text=f"Photo sent by {state.contact.display_name}",
        )
        message = result.text
        if message is None or not message.strip():
            message = await self._language.generate_text(
                prompt=image_message_prompt(
                    contact=state.contact,
                    turns=state.recent_turns,
                    current_message=state.request,
                    image_prompt=state.inspiration,
                )
            )
        await store.set_output(ChatAgentOutput(message=message.strip(), image=result.artifact))
