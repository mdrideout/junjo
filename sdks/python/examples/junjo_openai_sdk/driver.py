"""An application-owned Responses adapter; Junjo executes the Tool loop."""

import json
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.responses import ResponseFunctionToolCall

from junjo.agent import FinalOutputResponse, ModelRequest, ModelUsage, ToolCall, ToolCallsResponse
from junjo.agent.messages import message_to_json


class OpenAIModelDriver:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client
        self.model = model
        self.items: list[Any] = []
        self.seen_messages = 0

    async def request(self, request: ModelRequest) -> FinalOutputResponse | ToolCallsResponse:
        for message in request.messages[self.seen_messages :]:
            value = cast(dict[str, Any], message_to_json(message))
            match value["type"]:
                case "agent_input":
                    self.items.append({"role": "user", "content": json.dumps(value["input"])})
                case "assistant_output":
                    self.items.append({"role": "assistant", "content": json.dumps(value["output"])})
                case "tool_result":
                    self.items.append(
                        {
                            "type": "function_call_output",
                            "call_id": value["callId"],
                            "output": json.dumps(value["result"]),
                        }
                    )
                case "assistant_tool_calls":
                    # Historical normalized calls. Current-run provider output is retained below.
                    for call in value["calls"]:
                        self.items.append(
                            {
                                "type": "function_call",
                                "call_id": call["id"],
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            }
                        )
        payload = cast(dict[str, Any], request.to_json())
        response = await self.client.responses.create(
            model=self.model,
            instructions=request.instructions,
            input=self.items,
            tools=[
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"],
                    "strict": True,
                }
                for tool in payload["tools"]
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "support_answer",
                    "schema": payload["outputSchema"],
                    "strict": True,
                }
            },
            store=False,
            include=["reasoning.encrypted_content"],
        )
        if response.status != "completed":
            raise RuntimeError(f"OpenAI response did not complete: {response.status}")
        # Keep all output, including provider reasoning items needed by subsequent requests.
        self.items.extend(response.output)
        self.seen_messages = len(request.messages) + 1  # Junjo appends the normalized assistant decision.
        usage = (
            None
            if response.usage is None
            else ModelUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cached_input_tokens=response.usage.input_tokens_details.cached_tokens,
                reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens,
                total_tokens=response.usage.total_tokens,
            )
        )
        calls = [
            ToolCall(id=item.call_id, name=item.name, arguments=json.loads(item.arguments))
            for item in response.output
            if isinstance(item, ResponseFunctionToolCall)
        ]
        if calls:
            return ToolCallsResponse(tool_calls=calls, assistant_text=response.output_text or None, usage=usage)
        return FinalOutputResponse(output=json.loads(response.output_text), usage=usage)
