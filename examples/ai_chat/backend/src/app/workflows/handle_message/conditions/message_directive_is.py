from junjo.condition import Condition

from app.workflows.handle_message.schemas import MessageDirective
from app.workflows.handle_message.store import MessageWorkflowState


class MessageDirectiveIs(Condition[MessageWorkflowState]):

    def __init__(self, directive: MessageDirective):
        self.directive = directive

    def evaluate(self, state: MessageWorkflowState) -> bool:

        # Check the message_directive
        message_directive = state.message_directive
        if not message_directive:
            return False

        if message_directive == self.directive:
            return True

        return False

    def __str__(self) -> str:
        """
        Custom string representation override for this instance.
        """
        return f"MessageDirectiveIs({self.directive.name})"
