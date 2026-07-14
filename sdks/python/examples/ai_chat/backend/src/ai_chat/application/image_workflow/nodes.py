"""Known deterministic steps for image preparation and rendering."""

from junjo import Node

from ai_chat.domain.ports import ImageRenderer

from .state import ImageWorkflowStore


class PrepareImagePromptNode(Node[ImageWorkflowStore]):
    """Normalize the requested prompt and derive accessible display text."""

    async def service(self, store: ImageWorkflowStore) -> None:
        state = await store.get_state()
        prompt = " ".join(state.prompt.split())
        if not prompt:
            raise ValueError("An image prompt is required.")
        await store.set_prepared_prompt(
            prompt=prompt,
            alt_text=f"Deterministic illustration: {prompt}",
        )


class RenderImageNode(Node[ImageWorkflowStore]):
    """Delegate the explicit image side effect to an application adapter."""

    def __init__(self, renderer: ImageRenderer) -> None:
        super().__init__()
        self._renderer = renderer

    async def service(self, store: ImageWorkflowStore) -> None:
        state = await store.get_state()
        if state.prepared_prompt is None or state.alt_text is None:
            raise RuntimeError("The image prompt must be prepared before rendering.")
        artifact = await self._renderer.render(
            prompt=state.prepared_prompt,
            alt_text=state.alt_text,
        )
        await store.set_artifact(artifact)
