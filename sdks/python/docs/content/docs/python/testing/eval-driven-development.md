---
title: "Eval-Driven Development"
description: "Design targeted evaluations that ground recursive self improvement in measured outcomes. Use Studio datasets and runs alongside local pytest checks."
---
<!-- migrated-from: sdks/python/docs/eval_driven_dev.rst; source-hash: sha256:86b355297840f3d79ccab212f3e01dc7c3110d01ea7b271d810be5f8a6708255 -->

<a id="eval-driven-dev"></a>
Eval-driven development is the measurement practice inside
[recursive self improvement](/docs/recursive-self-improvement/). Define the
behavior you want, run representative scenarios, inspect failures, change the
application, and compare the results against the same criteria.

Junjo's Python SDK supplies targets, evaluators, and local execution tooling.
Junjo AI Studio stores datasets, outcomes, and execution evidence. Your coding
agent can operate that cycle from a natural-language request:

> Investigate this failed refund interaction in Junjo: [Studio trace link]. Build scenarios from the affected
> customer interactions, define the conditions for a correct outcome, and
> compare a targeted prompt change with the baseline. Show me the failures,
> regressions, and execution evidence.

The [evaluation datasets and runs guide](/docs/python/evaluation/) covers setup,
the coding-agent skill, the CLI, locking, and exact evidence queries. This page
focuses on choosing useful evaluations and testing individual implementation
boundaries.

## From an observed failure to a useful evaluation

Suppose a support agent rejects a damaged-item return because it applies the
ordinary return window. Inspect the recorded policy lookup and decision before
editing the prompt. Create a scenario with that input and an explicit criterion:
the damaged-item exception must be considered, without granting refunds for
unrelated ordinary returns.

Add positive, negative, and boundary cases to a draft dataset. If the existing
dataset is locked, create a new dataset containing the retained cases and the
new scenarios, then run both baseline and candidate against that same locked
set. Generated output is an observation, not the expected answer.

Evaluate the affected specialist or Node for fast feedback, then rerun the
complete flow to check routing and synthesis. Count operational errors
separately from failed judgments. A higher pass rate with lower judged coverage
may hide missing evidence; neither result proves behavior outside the cases
and criteria you tested.

<a id="powered-by-pytest"></a>
## Local correctness tests with pytest

Pytest is useful for source-colocated assertions, deterministic fixtures, and
CI checks. It complements the SDK's Studio-backed dataset and run lifecycle;
it is not the underlying implementation of `junjo eval`.

- Check an individual Node or complete Workflow through its public execution API.
- Exercise failure handling with deterministic fixtures.
- Run live model judgments when the test environment has the required services.
- Keep local test results in pytest, or use the evaluation framework when shared
  dataset history, structured outcomes, and evidence queries are needed.

Pytest executions can initialize an input state for the node, execute the real
Node through Junjo's normal lifecycle, and analyze the detached resulting
state. Use [`evaluate_node`](/docs/python/api/junjo/evaluate_node/) for Node-level evals; do not call
`Node.service()` directly.

## Prerequisites

- The worked example below lives in the junjo repository's `examples/base` app, so clone the [junjo repository](https://github.com/mdrideout/junjo) to run it
- Install `pytest` and `pytest-asyncio` in the environment used to run the evals (the example's async tests use `@pytest.mark.asyncio`)
- Live eval execution requires `GEMINI_API_KEY` in the environment used to run pytest

## Library Example

Check out `examples/base/src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test` to see an example eval system, setup to evaluate the joke created.

- [Github link to test example](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/base/src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test)
- It uses a combination of asserts and live LLM evaluations
- This example uses Gemini to evaluate the results of the `create_joke_node` against several test inputs inside `test_cases.py`
- The eval has a prompt inside `test_prompt.py`
- `test_node.py` executes the pytest test
- The live `node.py` LLM call is executed to generate the result and state update for evaluation
- Test failures include reasons why the prompt failed to generate output that passed the evaluation. See the `test_schema.py`.

The following is a condensed version of the eval test in `test_node.py`. Each test case in `test_cases.py` is a dictionary containing only the state fields the node requires, making it easy to build large eval sets by mocking node input state.

```python
import pytest

from junjo import ExecutionCorrelation, evaluate_node

from base.sample_workflow.sample_subflow.nodes.create_joke_node.node import CreateJokeNode
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_cases import test_cases
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_service import eval_create_joke_node
from base.sample_workflow.sample_subflow.store import SampleSubflowState, SampleSubflowStore

@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("test_case", test_cases)  # e.g. {"items": ["cat", "lasers", "space"]}
async def test_create_joke_node(test_case: dict):
    # Initialize the node's input state from the test case
    initial_state = SampleSubflowState.model_validate(test_case)
    assert initial_state.items is not None
    store = SampleSubflowStore(initial_state=initial_state)

    # Execute the real Node through a one-Node evaluation Workflow. This
    # preserves Node, Store, trace, and correlation evidence.
    node = CreateJokeNode()
    execution = await evaluate_node(
        node=node,
        store=store,
        correlation=ExecutionCorrelation(
            type="base.eval_case",
            id="|".join(test_case["items"]),
        ),
    )

    # Assert against the resulting state
    state_result = execution.state
    assert state_result.joke

    # Evaluate the joke - run the LLM evaluator service
    eval_result = await eval_create_joke_node(state_result.joke, initial_state.items)
    assert eval_result.passed, f"Joke evaluation failed: {eval_result.reason}"
```

Calibrate an evaluator before using its results to compare application changes.
Exercise a known-good output, a known-bad output, and a boundary case; review false
passes and false failures. Keep each evaluator focused on one understandable
product claim, return a binary decision with the deciding reason, and prefer a
deterministic check when the fact itself is deterministic. An LLM judge should
handle only the part of the claim that genuinely requires judgment.

Run the sample eval from `examples/base`:

```bash
uv run --package base -m pytest src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test/test_node.py -v
```

Expand the case set as new failure modes appear. A finite test suite measures
the represented behaviors; review coverage and evaluator quality before using
its pass rate to justify an application change.

The generated evaluation Workflow is intentional evidence. Junjo AI Studio
shows it as a one-Node Graph, and `execution.run_id` identifies the exact run
for a judge result.

This pytest pattern remains useful for source-colocated experiments. For
shared, locked input datasets, resumable baseline/candidate Runs, structured
results, coding-agent operation, and exact Studio evidence queries, use
[evaluation datasets and runs](/docs/python/evaluation/). That supported SDK
surface owns the dataset and Attempt mechanics while the application still
owns its domain inputs, construction, and judgment meaning.

## Testing Model Changes

Hold the cases and criteria constant while testing a different model, a focused
prompt, or concurrent operations. Compare quality together with measured
duration and available token usage. Include routing and synthesis in the
end-to-end measurement: faster individual calls do not automatically make the
whole application faster or cheaper.
