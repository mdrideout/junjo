"""Avatar Subflow and its explicit parent-state handoffs."""

from junjo import Graph, Node, Subflow

from ai_chat.domain.ports import ImageRenderer

from .avatar_state import AvatarWorkflowState, AvatarWorkflowStore
from .state import ContactWorkflowState, ContactWorkflowStore


class RenderAvatarNode(Node[AvatarWorkflowStore]):
    def __init__(self, renderer: ImageRenderer) -> None:
        super().__init__()
        self._renderer = renderer

    async def service(self, store: AvatarWorkflowStore) -> None:
        state = await store.get_state()
        artifact = await self._renderer.render(
            prompt=state.prompt,
            alt_text=state.alt_text,
        )
        await store.set_artifact(artifact)


def create_avatar_graph(renderer: ImageRenderer) -> Graph:
    render = RenderAvatarNode(renderer)
    return Graph(source=render, sinks=[render], edges=[])


class AvatarSubflow(
    Subflow[
        AvatarWorkflowState,
        AvatarWorkflowStore,
        ContactWorkflowState,
        ContactWorkflowStore,
    ]
):
    async def pre_run_actions(
        self,
        parent_store: ContactWorkflowStore,
        subflow_store: AvatarWorkflowStore,
    ) -> None:
        state = await parent_store.get_state()
        if None in (
            state.first_name,
            state.last_name,
            state.age,
            state.city,
            state.personality,
        ):
            raise RuntimeError("Contact identity must exist before avatar creation.")
        display_name = f"{state.first_name} {state.last_name}"
        await subflow_store.set_request(
            prompt=(
                f"Friendly profile portrait of {display_name}, age {state.age}, from {state.city}; {state.personality}."
            ),
            alt_text=f"Portrait of {display_name}",
        )

    async def post_run_actions(
        self,
        parent_store: ContactWorkflowStore,
        subflow_store: AvatarWorkflowStore,
    ) -> None:
        state = await subflow_store.get_state()
        if state.artifact is None:
            raise RuntimeError("Avatar Subflow produced no artifact.")
        await parent_store.set_avatar(state.artifact)
