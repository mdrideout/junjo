"""Per-call shared image-response Workflow factory."""

from junjo import Workflow

from ai_chat.domain.models import CompletedTurn, ContactProfile, CreateImageInput
from ai_chat.domain.ports import ImageModel, LanguageModel

from .graph import create_image_graph
from .state import ImageWorkflowState, ImageWorkflowStore


def create_image_workflow(
    request: CreateImageInput,
    *,
    contact: ContactProfile,
    recent_turns: tuple[CompletedTurn, ...],
    language: LanguageModel,
    images: ImageModel,
) -> Workflow[ImageWorkflowState, ImageWorkflowStore]:
    return Workflow(
        name="Create Chat Image Workflow",
        graph_factory=lambda: create_image_graph(language=language, images=images),
        store_factory=lambda: ImageWorkflowStore(
            initial_state=ImageWorkflowState(
                request=request.prompt,
                contact=contact,
                recent_turns=recent_turns,
            )
        ),
        max_iterations=1,
    )
