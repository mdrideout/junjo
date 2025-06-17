# Junjo Example - RunForEvery

This example demonstrates Junjo's RunForEvery async execution concent. `RunForEvery()` will execute a `Node`, `RunConcurrent`, or `Subflow` for every element in a list, concurrently.

This is helpful when you have a list of items in state, and need to execute a process against every element in the list.

### Run the example

> Note: the following commands assume your terminal is located in this directory.

- The graph workflow will run, logging node executions and state changes.
- If [Junjo Server](https://github.com/mdrideout/junjo-server) is running, it will receive telemetry.
  - Requires you to generate an API key inside the Junjo Server interface, and add it as a `.env` variable here.

```bash
# Run commands from this directory
#   - (Using uv package manager https://docs.astral.sh/uv/)
#
# Create a virtual environment if one doesn't exist yet (tested down to python 3.11)
$ uv venv --python 3.11

# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e ".[dev]"

# Run from this directory
$ python -m src.run_for_every.main

# Generate Graphviz renderings of the graph (outputs to graphviz_out dir in root)
$ python -m src.run_for_every.visualize
```

## Eval Driven Development

Eval-Driven Development (EDD) is a critical development strategy for applications powered by Large Language Models (LLMs). This practice places continuous and rigorous evaluation at the heart of the development lifecycle.

EDD accelerates complex workflow development by allowing one to iterate on their LLM prompts with many test inputs, and immediately see how the prompt changes impact the evaluation results.

**Example:** Check out `src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test` to see an example eval system, setup to evaluate the joke created. 

- The eval system is powered by **pytest**'
  - No third party tools or platforms are required - everything happens directly in your codebase
- It uses a combination of asserts and live LLM evaluations
- This example uses Gemini to evaluate the results of the `create_joke_node` against several test inputs inside `test_cases.py`
- The eval has a prompt inside `test_prompt.py`
- `test_node.py` executes the pytest test
- The live `node.py` LLM call is executed to generate the result and state update for evaluation
- Test failures include reasons why the prompt failed to generate output that passed the evaluation. See the `test_schema.py`.

On mission critical workflows, this setup can be used to orchestrate hundreds or thousands of test inputs against a prompt to ensure it covers all use cases well.

#### Testing Model Changes

This is also a great way to evaluate whether changing LLM models increases or decreases eval pass / fail rates, or changes the speed at which evals are completed.

#### Running The `create_joke_node` eval:

```bash
# Run the pytest command from this directory.
# Ensure you have setup the appropriate environment from the above "Run the example" instructions
$ python -m pytest src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test/test_node.py

# This test is intentially tough to fail at least a few times for demonstration.
```
