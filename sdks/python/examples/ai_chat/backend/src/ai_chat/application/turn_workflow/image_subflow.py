"""Explicit parent/child handoff for the known image-response branch."""

from junjo import Subflow

from ai_chat.application.image_workflow.state import (
    ImageWorkflowState,
    ImageWorkflowStore,
)
from ai_chat.domain.models import ChatAgentOutput

from .state import TurnWorkflowState, TurnWorkflowStore


class ImageResponseSubflow(
    Subflow[
        ImageWorkflowState,
        ImageWorkflowStore,
        TurnWorkflowState,
        TurnWorkflowStore,
    ]
):
    async def pre_run_actions(
        self,
        parent_store: TurnWorkflowStore,
        subflow_store: ImageWorkflowStore,
    ) -> None:
        parent_state = await parent_store.get_state()
        await subflow_store.set_prompt(parent_state.turn.user_message.content)

    async def post_run_actions(
        self,
        parent_store: TurnWorkflowStore,
        subflow_store: ImageWorkflowStore,
    ) -> None:
        subflow_state = await subflow_store.get_state()
        if subflow_state.artifact is None:
            raise RuntimeError("The image response Subflow produced no artifact.")
        await parent_store.set_response(
            ChatAgentOutput(
                message="I made this image for you.",
                image=subflow_state.artifact,
            )
        )
