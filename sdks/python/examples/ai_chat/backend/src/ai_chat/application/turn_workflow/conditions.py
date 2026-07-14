"""Pure branch conditions for the restored handle-message Graph."""

from junjo import Condition

from ai_chat.domain.models import MessageDirective

from .state import TurnWorkflowState


class DirectiveIs(Condition[TurnWorkflowState]):
    def __init__(self, directive: MessageDirective) -> None:
        self._directive = directive

    def evaluate(self, state: TurnWorkflowState) -> bool:
        return state.directive is self._directive

    def __str__(self) -> str:
        return f"Directive is {self._directive.value}"
