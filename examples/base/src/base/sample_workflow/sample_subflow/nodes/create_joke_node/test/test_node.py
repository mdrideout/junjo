

# Running this test:
# pytest src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test/test_node.py
#
# This test is intentially tough to fail at least a few times for demonstration.

import pytest

from base.sample_workflow.sample_subflow.nodes.create_joke_node.node import CreateJokeNode
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_cases import test_cases
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_service import eval_create_joke_node
from base.sample_workflow.sample_subflow.store import SampleSubflowState, SampleSubflowStore


class TestCreateJokeNode:
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("test_case", test_cases)
    async def test_create_joke_node_valid_directives(
        self, test_case: dict
    ):
        """
        Test that the node sets the correct message_directive for valid messages.
        """
        # Arrange
        print(f"Running test case: {test_case}")

        # Initialize the state for this node execution
        initial_state = SampleSubflowState.model_validate(test_case)
        assert initial_state.items is not None

        store = SampleSubflowStore(initial_state=initial_state)
        node = CreateJokeNode()

        # Execute the node service
        await node.service(store)

        # Get the resulting state
        state_result = await store.get_state()
        joke_result = state_result.joke

        # Assert that the joke is not None
        assert joke_result is not None
        assert joke_result != ""

        # Evaluate the joke - run the LLM evaluator service
        eval_result = await eval_create_joke_node(joke_result, initial_state.items)

        # Assert that the evaluation result is True
        assert eval_result.passed, f"Joke evaluation failed: {eval_result.reason}"

