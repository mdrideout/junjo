"""Per-call image Workflow factory."""

from junjo import Workflow

from ai_chat.domain.models import CreateImageInput
from ai_chat.domain.ports import ImageRenderer

from .graph import create_image_graph
from .state import ImageWorkflowState, ImageWorkflowStore


def create_image_workflow(
    request: CreateImageInput,
    renderer: ImageRenderer,
) -> Workflow[ImageWorkflowState, ImageWorkflowStore]:
    """Return a fresh Workflow whose factories close over detached call data."""

    prompt = request.prompt
    return Workflow(
        name="Create Chat Image Workflow",
        graph_factory=lambda: create_image_graph(renderer),
        store_factory=lambda: ImageWorkflowStore(initial_state=ImageWorkflowState(prompt=prompt)),
        max_iterations=1,
    )
