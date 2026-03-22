import asyncio

import pytest
from pydantic import model_validator

from junjo import BaseState, BaseStore


class MeetingWindowState(BaseState):
    start_time: int
    end_time: int

    @model_validator(mode="after")
    def validate_window(self) -> "MeetingWindowState":
        if self.end_time < self.start_time:
            raise ValueError("end_time must be >= start_time")
        return self


class MeetingWindowStore(BaseStore[MeetingWindowState]):
    async def set_start_time(self, start_time: int) -> None:
        await self.set_state({"start_time": start_time})

    async def set_end_time(self, end_time: int) -> None:
        await self.set_state({"end_time": end_time})


@pytest.mark.asyncio
async def test_set_state_validates_against_locked_current_state() -> None:
    store = MeetingWindowStore(
        initial_state=MeetingWindowState(start_time=1, end_time=5)
    )

    # Hold the store lock so both updates queue behind it. With the old
    # implementation, both updates validate before the lock is released and
    # then commit against stale assumptions. With the fixed implementation,
    # validation happens under the lock against the real current state.
    await store._lock.acquire()

    first_update = asyncio.create_task(store.set_start_time(4))
    await asyncio.sleep(0)
    second_update = asyncio.create_task(store.set_end_time(3))
    await asyncio.sleep(0)

    store._lock.release()

    first_result, second_result = await asyncio.gather(
        first_update,
        second_update,
        return_exceptions=True,
    )

    assert first_result is None
    assert isinstance(second_result, ValueError)

    current_state = await store.get_state()
    assert current_state.start_time == 4
    assert current_state.end_time == 5
