

import nanoid
from junjo import Workflow
from junjo.telemetry.hook_manager import HookManager

from run_for_every.sample_workflow.graph import sample_workflow_graph
from run_for_every.sample_workflow.schemas import Task
from run_for_every.sample_workflow.store import SampleWorkflowState, SampleWorkflowStore

# Create a task list
task_strings = [
    "Wash the dishes",
    "Take the dog for a walk",
    "Weed the gargen",
    "Workout at the gym",
    "Cook dinner for myself"
]

# Prepare the task list for the initial_state by creating ids and constructing the Task objects
tasks: dict[str, Task] = {}
for task_string in task_strings:
    id = nanoid.generate(size=6)
    tasks[id] = Task(id=id, name=task_string)

# Create the workflow
sample_workflow = Workflow[SampleWorkflowState, SampleWorkflowStore](
    name="demo_base_workflow",
    graph=sample_workflow_graph,
    store_factory=lambda: SampleWorkflowStore(
        initial_state=SampleWorkflowState(tasks=tasks) # Set the tasks into the initial_state
    ),
    hook_manager=HookManager(verbose_logging=False, open_telemetry=True),
)
