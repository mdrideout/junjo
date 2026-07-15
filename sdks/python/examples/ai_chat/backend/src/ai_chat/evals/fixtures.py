"""Explicit application fixtures used only by deliberate live evaluations."""

from ai_chat.bootstrap import ChatApplication, ProviderRuntime
from ai_chat.domain.models import (
    ChatAgentOutput,
    ContactProfile,
    ContactSex,
    ContextPolicyReference,
    Conversation,
    ConversationOverview,
    ImageArtifact,
    PersonalityTraits,
    Turn,
)


def require_provider_runtime(application: ChatApplication) -> ProviderRuntime:
    """Return the real runtime that ``live_application`` always composes."""

    runtime = application.provider_runtime
    if runtime is None:
        raise RuntimeError("Live evaluation requires a real provider runtime.")
    return runtime


async def create_fixed_contact(
    application: ChatApplication,
    *,
    with_local_avatar: bool,
) -> ConversationOverview:
    """Persist one stable persona, generating an avatar only when needed."""

    if with_local_avatar:
        avatar = await application.images.generate(
            prompt=(
                "Ultra-realistic square dating profile portrait of a 32-year-old woman "
                "named Maya Chen, relaxed natural expression, shoulder-length dark hair, "
                "casual denim jacket, outdoors in Brooklyn in soft daylight, normal human "
                "proportions, no text, no watermark."
            ),
            alt_text="Portrait of Maya Chen",
        )
    else:
        avatar = ImageArtifact(
            id="eval-avatar",
            url="/api/images/eval-avatar.png",
            alt_text="Portrait of Maya Chen",
        )
    contact = ContactProfile(
        id="eval-contact",
        first_name="Maya",
        last_name="Chen",
        sex=ContactSex.FEMALE,
        age=32,
        personality=PersonalityTraits(
            openness=0.83,
            conscientiousness=0.72,
            extraversion=0.61,
            agreeableness=0.79,
            neuroticism=0.24,
            intelligence=0.82,
            religiousness=0.18,
            attractiveness=0.76,
            trauma=0.16,
        ),
        latitude=40.6782,
        longitude=-73.9442,
        city="Brooklyn",
        state="NY",
        bio=(
            "I am a landscape architect at Greenline Studio in Brooklyn. I spend "
            "weekends at pottery classes, cooking for my younger brother, and walking "
            "Prospect Park with a film camera."
        ),
        avatar=avatar,
    )
    conversation = Conversation(
        id="eval-conversation",
        title=contact.display_name,
        contact_id=contact.id,
    )
    return await application.store.create_contact(
        contact=contact,
        conversation=conversation,
    )


async def seed_completed_turn(
    application: ChatApplication,
    *,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> Turn:
    """Persist explicit historical input without pretending it is model evidence."""

    turn = await application.store.admit_turn(
        conversation_id=conversation_id,
        turn_id=f"eval-history-{len(await application.store.list_turns(conversation_id)) + 1}",
        text=user_message,
        context_policy=ContextPolicyReference(),
    )
    await application.store.start_turn(turn.id)
    await application.store.record_turn_outcome(
        turn_id=turn.id,
        output=ChatAgentOutput(message=assistant_message),
        agent_run_id=None,
    )
    return await application.store.complete_turn(
        turn_id=turn.id,
        workflow_run_id=f"eval-input-fixture-{turn.id}",
    )
