
import pytest
from loguru import logger

from app.workflows.create_contact.nodes.create_bio.node import (
    CreateBioNode,
)
from app.workflows.create_contact.nodes.create_bio.test.test_cases import test_cases
from app.workflows.create_contact.nodes.create_bio.test.test_service import eval_create_bio_node
from app.workflows.create_contact.store import (
    CreateContactState,
    CreateContactStore,
)

# Running this test:
# pytest src/app/workflows/create_contact/nodes/create_bio/test/test_node.py

class TestCreateBioNode:
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("test_case", test_cases)
    async def test_create_bio_node_valid_directives(
        self, test_case: dict
    ):
        """
        Test that the created contact bio fulfills our criteria.
        """
        # Arrange
        logger.info(f"Running test case: {test_case}")

        # Initialize the state for this node execution
        initial_state = CreateContactState.model_validate(test_case)
        store = CreateContactStore(initial_state=initial_state)
        node = CreateBioNode()

        # Act
        await node.service(store)
        state_result = await store.get_state()

        # Get the bio from the state
        bio_result = state_result.bio

        # Assert that the bio is not None
        assert bio_result is not None
        assert bio_result != ""

        # Evaluate the bio - run the LLM evaluator service
        eval_result = await eval_create_bio_node(bio_result)

        # Assert that the evaluation result is True
        assert eval_result.passed, f"Bio evaluation failed: {eval_result.reason}"

