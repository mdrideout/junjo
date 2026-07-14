"""Per-request create-contact Workflow factory."""

from junjo import Workflow

from ai_chat.domain.models import ContactSex
from ai_chat.domain.ports import ContactWriter, ImageModel, LanguageModel

from .graph import create_contact_graph
from .state import ContactWorkflowState, ContactWorkflowStore


def create_contact_workflow(
    *,
    contact_id: str,
    conversation_id: str,
    sex: ContactSex,
    contacts: ContactWriter,
    language: LanguageModel,
    images: ImageModel,
) -> Workflow[ContactWorkflowState, ContactWorkflowStore]:
    return Workflow(
        name="Create Contact Workflow",
        graph_factory=lambda: create_contact_graph(contacts=contacts, language=language, images=images),
        store_factory=lambda: ContactWorkflowStore(
            initial_state=ContactWorkflowState(
                contact_id=contact_id,
                conversation_id=conversation_id,
                sex=sex,
            )
        ),
        max_iterations=1,
    )
