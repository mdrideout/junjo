"""A stateless deterministic ModelDriver for a credential-free live demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import (
    AgentInputMessage,
    FinalOutputResponse,
    ModelRequest,
    ToolCall,
    ToolCallsResponse,
    ToolResultMessage,
)


class DemoModelDriver:
    """Select bounded capabilities from explicit message phrases."""

    async def request(self, request: ModelRequest) -> object:
        latest = request.messages[-1]
        if isinstance(latest, ToolResultMessage):
            return _final_from_tool(latest)

        current_input = next(
            message for message in reversed(request.messages) if isinstance(message, AgentInputMessage)
        )
        if not isinstance(current_input.input, Mapping):
            raise ValueError("ChatAgentInput must normalize to a JSON object.")
        input_value = cast(Mapping[str, object], current_input.input)
        text = str(input_value["message"])
        lowered = text.casefold()
        if any(word in lowered for word in ("image", "picture", "draw", "illustrate")):
            return ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id=f"image-{request.ordinal}",
                        name="create_image",
                        arguments={"prompt": text},
                    )
                ]
            )
        if any(word in lowered for word in ("history", "remember", "said before")):
            return ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id=f"history-{request.ordinal}",
                        name="search_conversation_history",
                        arguments={"query": _search_term(text), "limit": 5},
                    )
                ]
            )
        if any(word in lowered for word in ("contact", "profile", "who are you")):
            return ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id=f"contact-{request.ordinal}",
                        name="get_contact_profile",
                        arguments={"include_bio": True},
                    )
                ]
            )
        return FinalOutputResponse(output={"message": f"Deterministic reply: {text}", "image": None})


def demo_model_binding() -> ModelDriverBinding:
    """Return the declared identity and shared-safe stateless demo driver."""

    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="ai_chat_demo",
            provider="junjo",
            model="deterministic-demo-v1",
            settings={},
        ),
        driver=DemoModelDriver(),
    )


def _final_from_tool(message: ToolResultMessage) -> FinalOutputResponse:
    result = message.result
    if not isinstance(result, Mapping):
        raise ValueError("Demo Tool results must normalize to JSON objects.")
    result_value = cast(Mapping[str, object], result)
    if message.tool_name == "create_image":
        artifact = result_value["artifact"]
        return FinalOutputResponse(
            output={
                "message": "I created the requested deterministic illustration.",
                "image": artifact,
            }
        )
    if message.tool_name == "get_contact_profile":
        return FinalOutputResponse(
            output={
                "message": (f"This conversation is with {result_value['display_name']}: {result_value['bio']}"),
                "image": None,
            }
        )
    matches = result_value.get("matches", ())
    if not isinstance(matches, Sequence):
        raise ValueError("History Tool matches must be a JSON array.")
    summary = "; ".join(
        str(cast(Mapping[str, object], item)["content"])
        for item in matches
        if isinstance(item, Mapping) and "content" in item
    )
    return FinalOutputResponse(
        output={
            "message": summary or "I found no earlier matching messages.",
            "image": None,
        }
    )


def _search_term(text: str) -> str:
    words = [word.strip(".,!?;:'\"") for word in text.split()]
    meaningful = [word for word in words if len(word) >= 4 and word.casefold() != "history"]
    return meaningful[-1] if meaningful else "conversation"
