"""Model-powered avatar Subflow and explicit parent-state handoffs."""

from junjo import Edge, Graph, Node, Subflow

from ai_chat.domain.ports import ImageModel, LanguageModel

from .avatar_state import AvatarWorkflowState, AvatarWorkflowStore
from .prompts import avatar_generation_prompt, avatar_inspiration_prompt
from .state import ContactWorkflowState, ContactWorkflowStore


class CreateAvatarInspirationNode(Node[AvatarWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: AvatarWorkflowStore) -> None:
        state = await store.get_state()
        required = (
            state.personality,
            state.bio,
            state.city,
            state.state,
            state.first_name,
            state.last_name,
        )
        if any(value is None for value in required):
            raise RuntimeError("Avatar profile context is incomplete.")
        assert state.personality is not None
        assert state.bio is not None
        assert state.city is not None
        assert state.state is not None
        assert state.first_name is not None
        assert state.last_name is not None
        inspiration = await self._language.generate_text(
            prompt=avatar_inspiration_prompt(
                personality=state.personality,
                bio=state.bio,
                city=state.city,
                state=state.state,
                first_name=state.first_name,
                last_name=state.last_name,
            )
        )
        await store.set_inspiration(inspiration)


class CreateAvatarNode(Node[AvatarWorkflowStore]):
    def __init__(self, images: ImageModel) -> None:
        super().__init__()
        self._images = images

    async def service(self, store: AvatarWorkflowStore) -> None:
        state = await store.get_state()
        required = (
            state.inspiration,
            state.personality,
            state.bio,
            state.city,
            state.state,
            state.sex,
            state.age,
            state.first_name,
            state.last_name,
        )
        if any(value is None for value in required):
            raise RuntimeError("Avatar generation context is incomplete.")
        assert state.inspiration is not None
        assert state.personality is not None
        assert state.bio is not None
        assert state.city is not None
        assert state.state is not None
        assert state.sex is not None
        assert state.age is not None
        assert state.first_name is not None
        assert state.last_name is not None
        display_name = f"{state.first_name} {state.last_name}"
        artifact = await self._images.generate(
            prompt=avatar_generation_prompt(
                personality=state.personality,
                bio=state.bio,
                city=state.city,
                state=state.state,
                sex=state.sex,
                age=state.age,
                inspiration=state.inspiration,
            ),
            alt_text=f"Portrait of {display_name}",
        )
        await store.set_artifact(artifact)


def create_avatar_graph(*, language: LanguageModel, images: ImageModel) -> Graph:
    inspire = CreateAvatarInspirationNode(language)
    create = CreateAvatarNode(images)
    return Graph(source=inspire, sinks=[create], edges=[Edge(tail=inspire, head=create)])


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
        parent = await parent_store.get_state()
        required = (
            parent.personality,
            parent.bio,
            parent.city,
            parent.state,
            parent.age,
            parent.first_name,
            parent.last_name,
        )
        if any(value is None for value in required):
            raise RuntimeError("Contact identity must exist before avatar creation.")
        assert parent.personality is not None
        assert parent.bio is not None
        assert parent.city is not None
        assert parent.state is not None
        assert parent.age is not None
        assert parent.first_name is not None
        assert parent.last_name is not None
        await subflow_store.set_state(
            {
                "personality": parent.personality,
                "bio": parent.bio,
                "city": parent.city,
                "state": parent.state,
                "sex": parent.sex,
                "age": parent.age,
                "first_name": parent.first_name,
                "last_name": parent.last_name,
            }
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
