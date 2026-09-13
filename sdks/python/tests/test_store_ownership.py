from typing import Any

import pytest
from pydantic import BaseModel, model_validator

from junjo import BaseState, BaseStore


class Payload(BaseModel):
    values: list[int]


class State(BaseState):
    payload: Payload
    flexible: dict[str, Any] = {}


@pytest.mark.asyncio
async def test_nested_model_write_is_owned_and_reconstructable():
    store = BaseStore(State(payload=Payload(values=[0])))
    payload = Payload(values=[1])
    await store.set_state({"payload": payload})
    before = await store._get_store_owner_evidence()
    payload.values.append(999)
    after = await store._get_store_owner_evidence()
    assert (await store.get_state()).payload.values == [1]
    assert after.reconstructable and before.reconstructable
    assert after.revision_end == before.revision_end == 1


@pytest.mark.asyncio
async def test_model_inside_any_mapping_is_owned():
    store = BaseStore(State(payload=Payload(values=[0])))
    payload = Payload(values=[1])
    await store.set_state({"flexible": {"nested": payload}})
    payload.values.append(999)
    assert (await store.get_state()).flexible["nested"].values == [1]
    assert (await store._get_store_owner_evidence()).reconstructable


@pytest.mark.asyncio
async def test_shared_input_cannot_mutate_two_stores():
    stores = [BaseStore(State(payload=Payload(values=[0]))) for _ in range(2)]
    payload = Payload(values=[1])
    for store in stores:
        await store.set_state({"payload": payload})
    payload.values.append(999)
    for store in stores:
        assert (await store.get_state()).payload.values == [1]


class ValidatedState(State):
    @model_validator(mode="after")
    def normalize_then_reject(self):
        if self.payload.values == [2]:
            self.payload.values.append(3)
            raise ValueError("Rejected domain update")
        return self


@pytest.mark.asyncio
async def test_rejected_normalizing_validator_does_not_mutate_callers_input():
    store = BaseStore(ValidatedState(payload=Payload(values=[0])))
    payload = Payload(values=[2])
    with pytest.raises(ValueError):
        await store.set_state({"payload": payload})
    assert payload.values == [2]
    assert (await store.get_state()).payload.values == [0]
    assert (await store._get_store_owner_evidence()).revision_end == 0


@pytest.mark.asyncio
async def test_prospective_validation_does_not_mutate_callers_input():
    store = BaseStore(ValidatedState(payload=Payload(values=[0])))
    payload = Payload(values=[2])
    with pytest.raises(ValueError):
        await store._validate_state_update({"payload": payload})
    assert payload.values == [2]
    assert (await store._get_store_owner_evidence()).revision_end == 0
