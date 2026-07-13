import pytest

from app.db.models.contact.schemas import Sex
from app.workflows.create_contact.nodes.select_sex.node import SelectSexNode
from app.workflows.create_contact.store import CreateContactState, CreateContactStore


class TestSelectSexNode:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_does_not_override_preselected_sex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.workflows.create_contact.nodes.select_sex.node as select_sex_node_module

        monkeypatch.setattr(select_sex_node_module, "select_sex", lambda: Sex.FEMALE)

        store = CreateContactStore(initial_state=CreateContactState(sex=Sex.MALE))
        node = SelectSexNode()

        await node.service(store)
        state = await store.get_state()

        assert state.sex == Sex.MALE

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sets_sex_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.workflows.create_contact.nodes.select_sex.node as select_sex_node_module

        monkeypatch.setattr(select_sex_node_module, "select_sex", lambda: Sex.MALE)

        store = CreateContactStore(initial_state=CreateContactState())
        node = SelectSexNode()

        await node.service(store)
        state = await store.get_state()

        assert state.sex == Sex.MALE

