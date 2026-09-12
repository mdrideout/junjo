---
title: "Parallel workflow steps with RunConcurrent"
description: "Run independent AI workflow steps concurrently, commit distinct state fields safely, and compare latency and quality against the sequential baseline."
---
<!-- migrated-from: sdks/python/docs/concurrency.rst; source-hash: sha256:4c735f32174f03a137694d8b18faae97dd767ac4d67d735fa1de8c32f877ead7 -->
<!-- migrated-keywords: junjo, python, asyncio, concurrency, workflow execution, concurrent execution, immutable state -->

<a id="concurrency"></a>
`RunConcurrent` groups independent Nodes or Subflows into one graph step. A
single incoming edge starts the group; the next edge is traversed after its
children finish. For example, distill order history, product policy, and payment
facts concurrently before a synthesis Node consumes all three results.

This is a concrete optimization your coding agent can test during recursive
self improvement. Measure the entire workflow against the same
[evaluation dataset](/docs/python/evaluation/), including the synthesis step;
parallel calls do not by themselves establish better quality or lower cost.

## Asyncio Native: The Core of Junjo's Performance

Being "asyncio native" means Junjo is fundamentally built using Python's `async` and `await` syntax and leverages the `asyncio` event loop. This offers significant advantages:

- **Non-Blocking Operations**: Nodes can await asynchronous network clients without blocking the event loop. Synchronous file access or a blocking model client still blocks unless the application moves that work off the event loop.
- **Efficient Resource Utilization**: By avoiding thread-based parallelism for I/O-bound tasks, Junjo can handle many concurrent operations with lower overhead compared to traditional multi-threaded approaches.
- **Seamless Integration**: You can easily integrate other asyncio-compatible libraries within your Junjo workflows.

### Example: `RunConcurrent()`

When defining your workflow's graph or subflow, you can easily execute nodes and subflows concurrently.

```python
def create_record_workout_activity_graph() -> Graph:
  """
  Factory function to create a new instance of the workflow graph,
  so each workflow execution gets a fresh, isolated graph.
  """
  # Instantiate nodes
  count_activities = CountActivitiesNode()
  determine_when = DetermineWhenNode()
  activity_query_splitter = ActivityQuerySplitterNode()
  final_node = FinalNode()

  # Create a RunConcurrent instance, and specify the nodes to execute
  initial_analysis_node = RunConcurrent(
    name="Initial Analysis",
    items=[count_activities, determine_when]
  )

  # Define the graph structure
  return Graph(
    source=initial_analysis_node,
    sinks=[final_node],
    edges=[
        # Specify the RunConcurrent instance like any other Graph node
        Edge(tail=initial_analysis_node, head=activity_query_splitter, condition=IsMultipleActivities()),

        # Final transitions
        Edge(tail=activity_query_splitter, head=final_node),
        Edge(tail=initial_analysis_node, head=final_node),
    ]
  )

# Construct the workflow with factories so each execution
# creates a fresh, isolated graph and store
record_workout_activity_workflow = Workflow[RecordWorkoutActivityState, RecordWorkoutActivityStore](
  name="Record Workout Activity",
  graph_factory=create_record_workout_activity_graph,
  store_factory=lambda: RecordWorkoutActivityStore(
    initial_state=RecordWorkoutActivityState()
  )
)
```

The declared structure groups both analysis Nodes into one executable step:

```text
RunConcurrent: Initial Analysis
  ├─ CountActivitiesNode
  └─ DetermineWhenNode
       ↓ both complete
  IsMultipleActivities?
    yes → ActivityQuerySplitterNode → FinalNode
    no  → FinalNode
```

This example demonstrates how `RunConcurrent` can be utilized to execute nodes concurrently. You can also execute entire `Subflow` instances concurrently.

State commits made by these nodes flow through `set_state()`, which validates
and applies each committed update under the store lock. **Junjo AI Studio**
allows you to step through state updates incrementally to see which nodes
update state and when, even during high concurrency.

## Immutable State: Ensuring Concurrency Safety

One of the challenges in concurrent programming is managing shared state. When multiple nodes attempt to modify the same piece of data simultaneously, it can lead to race conditions, data corruption, and unpredictable behavior.

Junjo addresses this by promoting **immutable state updates** via a **store** layer.

1. **Stores define state update functions**: The store is responsible for managing the instance of state. Functions defined in the store call `set_state()` to validate and commit explicit state updates safely.
2. **Nodes execute state update functions**: Nodes receive access to the store, and can inspect state snapshots and call store actions.

The following state and store example demonstrates Junjo's redux-inspired state update pattern.

```python
# store.py
class SampleState(BaseState):
  data: str | None = None
  count: int = 0

class SampleStore(BaseStore[SampleState]):
    async def set_data(self, payload: str) -> None:
        await self.set_state({"data": payload})

    async def set_count(self, payload: int) -> None:
        await self.set_state({"count": payload})

    async def increment(self) -> None:
      await self.set_state({"count": self._state.count + 1})

    async def decrement(self) -> None:
        await self.set_state({"count": self._state.count - 1})

# node_set_data.py
class SetDataNode(Node[SampleStore]):
  async def service(self, store: SampleStore) -> None:
      # Get a detached snapshot of the current state and maybe do something with it
      state = await store.get_state()

      # Get some data
      data = fetch_data()

      # Update the store with the data
      await store.set_data(data)
      return

# node_increment.py
class IncrementNode(Node[SampleStore]):
  async def service(self, store: SampleStore) -> None:
      await store.increment()
      return

# node_decrement.py
class DecrementNode(Node[SampleStore]):
  async def service(self, store: SampleStore) -> None:
      await store.decrement()
      return
```

The above nodes could be executed concurrently using `RunConcurrent`. Each
committed `set_state()` call is validated and applied safely by the store.
The `increment` and `decrement` examples derive an update immediately before
committing it. The lock covers `set_state()`, not arbitrary work inside an
action. Do not add an `await` between reading a value and deriving its
replacement and assume that the whole read/modify/write operation is atomic.
When concurrent Nodes need independent results, patch distinct fields such as
`order_summary`, `policy_eligible`, and `paid_amount`. Coordinate application
operations explicitly when they depend on the same prior value. Outside Store
actions, read state with `await store.get_state()`.

This approach significantly simplifies reasoning about concurrent execution, as
you don't have to manage locks around individual state commits. `get_state()`
returns a detached snapshot for reads, and all real state changes still flow
through store actions that call `set_state()`.

## Benefits of Junjo's Approach to Concurrency

Junjo's concurrency model, combining asyncio-native design with immutable state and utilities like `RunConcurrent`, offers several key benefits:

- **Improved Performance and Throughput**: Efficiently handles I/O-bound tasks and concurrent execution, leading to faster workflow completion.
- **Simplified Development**: Writing asynchronous code is natural with `async/await`. Immutable state reduces the mental overhead of managing concurrent data access.
- **Enhanced Reliability and Stability**: Store commits are validated and applied under a lock, reducing the risk of state corruption and making workflow behavior easier to inspect.
- **Scalability**: Well-suited for building applications that need to handle a large number of concurrent operations or scale with increasing load.

## Best Practices for Designing Concurrent Junjo Workflows

When designing concurrent workflows with Junjo, consider the following:

- **Identify Independent Tasks**: Look for parts of your workflow that don't depend on each other's immediate output. These are good candidates for `RunConcurrent`.
- **Keep Nodes Focused**: Design nodes to perform specific, well-defined tasks. This makes it easier to reason about their concurrent behavior.
- **Understand State Flow**: Be clear about what state each concurrent branch needs and what state it will produce. Junjo's immutable state helps, but clear design is still key.
- **Understand Failure Ownership**: If a child fails, `RunConcurrent` cancels pending siblings, drains them, and re-raises the original failure. Already completed side effects remain real; the application owns transactions and recovery.
- **Profile and Optimize**: Use profiling tools to identify bottlenecks in your asynchronous workflows and optimize critical paths.

## Conclusion

Use `RunConcurrent` for independent work inside one application execution. Use
separate [evaluation Runs](/docs/python/evaluation/#execute-resume-and-compare)
when coding agents or worktrees are testing different implementations in
parallel. These are separate kinds of concurrency: the evaluation executor
runs cases sequentially, while an individual target may itself contain
concurrent workflow steps.
