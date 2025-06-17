from junjo.state import BaseState
from junjo.store import BaseStore

from run_for_every.sample_workflow.schemas import Task


class SampleWorkflowState(BaseState):
    tasks: dict[str, Task]

class SampleWorkflowStore(BaseStore[SampleWorkflowState]):

    async def set_task_duration(self, id: str, minutes: float) -> None:
        self._state.tasks[id].duration_minutes = minutes
