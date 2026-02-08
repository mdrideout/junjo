# Junjo Example: Base

This is a baseline Junjo example application meant to showcase:

- A single workflow
- The Graph
- A few top level nodes
- Concurrent execution
- A Subflow
- A Conditional that determines the next node based on the results of a state update
- Streaming telemetry to Junjo AI Studio for visualization and debugging

See the **ai_chat** example for a more advanced frontend / backend E2E experience that utilizes LLM API calls.

### Recommended Setup: Junjo AI Studio

Start an instance of [Junjo AI Studio Minimal Build](https://github.com/mdrideout/junjo-ai-studio-minimal-build) for a turn-key way to see how this example streams debugging telemetry. This is optional. Junjo works with any OpenTelemetry provider. 

### Run the example

> Note: you can run the following commands from this directory; `uv` will discover the workspace root automatically.

- The graph workflow will run, logging node executions and state changes to your console
- If [Junjo AI Studio](https://github.com/mdrideout/junjo-ai-studio-minimal-build) is running, it will receive telemetry.
  - Requires you to generate an API key inside the Junjo AI Studio interface, and add it as a `.env` variable here.

```bash
# (use uv package manager https://docs.astral.sh/uv/)
#
# Create a .env file from the .env.example 
#
# This repo is a `uv` workspace. The virtual environment lives at the repo root
# (`../../.venv` from here), not inside this example directory.
#
# Recommended (run from this directory):
$ uv sync --python 3.11 --package base --all-extras
$ uv run --package base -m base.main
$ uv run --package base -m base.visualize

# Standalone (if you copied this example out of the workspace):
# $ uv sync --all-extras
# $ uv run -m base.main
# $ uv run -m base.visualize
```

## Eval Driven Development

Eval-Driven Development (EDD) is a critical development strategy for applications powered by Large Language Models (LLMs). This practice places continuous and rigorous evaluation at the heart of the development lifecycle.

EDD accelerates complex workflow development by allowing one to iterate on their LLM prompts with many test inputs, and immediately see how the prompt changes impact the evaluation results.

**Example:** Open `src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test` to see an example eval system, setup to evaluate the joke created. 

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

## Running The Sample Evals: `create_joke_node`

This eval is strict and likely to fail all cases. This is to demonstrate the information provided by this eval pattern, that can inform improvements to prompts and workflow steps.

```bash
# Run the pytest command from this directory.
# Ensure you have setup the appropriate environment from the above "Run the example" instructions
$ python -m pytest src/base/sample_workflow/sample_subflow/nodes/create_joke_node/test/test_node.py -v
```
