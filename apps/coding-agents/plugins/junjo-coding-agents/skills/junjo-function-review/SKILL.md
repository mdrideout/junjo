---
name: junjo-function-review
description: Execute the Junjo FunctionReview proof with Codex reasoning and optional Studio diagnostics. Use when asked to run the Junjo coding-agent example or validate its subagent workflow.
---

# Junjo FunctionReview

Use the installed Junjo MCP tools. The local bridge must already be running.
If the tools are unavailable, report that; do not substitute shell execution
or call a model API.

The coordinator starts an execution with `start_execution`. Set `capture=true`
when the user requests diagnostic capture; otherwise leave it false. Host
telemetry export must also be configured for model spans to appear.

For the concurrent proof, spawn two native Codex subagents. Give each the
execution ID and one fixture (`buggy` or `correct`). Each subagent:

1. Calls `start_review(execution_id, fixture)` once.
2. Reads the returned instructions, input, and output schema.
3. Uses its own reasoning to produce the result, then calls
   `complete_step(request_id, result)`.
4. Prints the complete tool response unchanged. Its receipt lets the bridge
   correlate the actual Codex request without guessing from timestamps.
5. If the response has `status=work`, reasons about that next step in a new
   model response and repeats. Never precompute both steps in one tool script.
6. Returns the final workflow result to the coordinator.

The coordinator waits for both subagents and calls `finish_execution`.
For a single-worker proof, perform the same worker loop in one subagent.
Use `finish_execution(cancel=true)` when the user cancels this execution.
Do not edit the snippets: the example asks for review evidence only.

`execution_status` reports submitted steps and observed model-span counts.
Host export is asynchronous, so workflow completion can precede model evidence.
Report zero model spans as missing evidence, not successful model tracing.
