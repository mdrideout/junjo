"""Application service for contact creation and persistence."""

from junjo import ExecutionCorrelation

from ai_chat.domain.models import ContactSex, ConversationOverview
from ai_chat.domain.ports import ContactWriter, IdFactory, ImageModel, LanguageModel

from .factory import create_contact_workflow


class ContactCreationService:
    def __init__(
        self,
        *,
        contacts: ContactWriter,
        language: LanguageModel,
        images: ImageModel,
        id_factory: IdFactory,
    ) -> None:
        self._contacts = contacts
        self._language = language
        self._images = images
        self._id_factory = id_factory

    async def create(self, sex: ContactSex) -> ConversationOverview:
        contact_id = self._id_factory()
        conversation_id = self._id_factory()
        workflow = create_contact_workflow(
            contact_id=contact_id,
            conversation_id=conversation_id,
            sex=sex,
            contacts=self._contacts,
            language=self._language,
            images=self._images,
        )
        result = await workflow.execute(correlation=ExecutionCorrelation(type="ai_chat.contact", id=contact_id))
        if result.state.result is None:
            raise RuntimeError("Create Contact Workflow produced no result.")
        return result.state.result
