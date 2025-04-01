
import pytest

from app.workflows_junjo.handle_message.nodes.assess_message_directive.node import (
    AssessMessageDirectiveNode,
)
from app.workflows_junjo.handle_message.nodes.assess_message_directive.test_cases import test_cases
from app.workflows_junjo.handle_message.store import (
    MessageWorkflowState,
    MessageWorkflowStore,
)


class TestAssessMessageDirectiveNode:
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("test_case", test_cases)
    async def test_assess_message_directive_node_valid_directives(
        self, test_case: dict
    ):
        """
        Test that the node sets the correct message_directive for valid messages.
        """
        # Arrange
        state_input = test_case["state_input"]
        state_expected = test_case["state_expected"]

        # Initialize the state for this node execution
        initial_state = MessageWorkflowState.model_validate(state_input)
        store = MessageWorkflowStore(initial_state=initial_state)
        node = AssessMessageDirectiveNode()

        # Act
        await node.service(store)
        state_result = await store.get_state()

        # Assert
        for key, value in state_expected.items():
            assert getattr(state_result, key) == value
