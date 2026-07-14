"""Explicit parent/child handoff for the shared image-response Workflow."""

from junjo import Subflow

from ai_chat.application.image_workflow.state import ImageWorkflowState, ImageWorkflowStore

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
        parent = await parent_store.get_state()
        if parent.contact is None:
            raise RuntimeError("Contact must be loaded before the image-response Subflow.")
        await subflow_store.set_state(
            {
                "request": parent.turn.user_message.content,
                "contact": parent.contact,
                "recent_turns": parent.recent_turns,
            }
        )

    async def post_run_actions(
        self,
        parent_store: TurnWorkflowStore,
        subflow_store: ImageWorkflowStore,
    ) -> None:
        child = await subflow_store.get_state()
        if child.output is None:
            raise RuntimeError("The image-response Subflow produced no output.")
        await parent_store.set_response(child.output)
