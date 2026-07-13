# ADR-0001: Disable xAI Responses API storage

- Status: Accepted
- Date: 2026-02-01

## Context

The xAI Responses API supports server-side conversation state by storing previous request/response messages. This can be convenient, but this app explicitly manages and submits chat history on the client side (or within the workflow) and does **not** want xAI to store conversation context.

## Decision

`GrokTool` always disables server-side conversation storage by creating chats with:

- `store_messages=False`

Additionally, `GrokTool` does not use `previous_response_id`-style chaining; callers must provide the full message history they want the model to consider.

## Consequences

- Privacy/retention: xAI is instructed not to store conversation state for our responses requests.
- Request size: callers must send the full conversation context each time (or a summarized version).
- No server-side continuity: features that rely on stored history or `previous_response_id` will not work by design.

## References

- xAI Chat/Responses guide (disable storing): https://docs.x.ai/docs/guides/chat#disable-storing-previous-requestresponse-on-server
