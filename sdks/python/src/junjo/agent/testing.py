"""Deterministic provider-free collaborators for Agent tests and examples."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .messages import ModelRequest


@dataclass(frozen=True, slots=True)
class ScriptedResponse:
    """Return one normalized response candidate for the next request."""

    value: object


@dataclass(frozen=True, slots=True)
class ScriptedError:
    """Raise one explicit exception for the next request."""

    error: Exception


ScriptedStep = ScriptedResponse | ScriptedError


class ScriptedModelDriver:
    """Consume a fixed response/error script while capturing immutable requests."""

    def __init__(self, steps: Sequence[ScriptedStep | object]) -> None:
        """Create a deterministic driver from ordered response/error steps.

        :param steps: Raw response candidates, ``ScriptedResponse`` values, or
            ``ScriptedError`` values. One step is consumed per request.
        """
        self._steps = tuple(
            step
            if isinstance(step, ScriptedResponse | ScriptedError)
            else ScriptedResponse(step)
            for step in steps
        )
        self._cursor = 0
        self._requests: list[ModelRequest] = []

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        """Return captured immutable normalized requests in invocation order."""

        return tuple(self._requests)

    async def request(self, request: ModelRequest) -> object:
        if self._cursor >= len(self._steps):
            raise RuntimeError("ScriptedModelDriver has no remaining response step.")
        self._requests.append(request)
        step = self._steps[self._cursor]
        self._cursor += 1
        if isinstance(step, ScriptedError):
            raise step.error
        return step.value
