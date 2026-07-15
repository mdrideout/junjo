"""Common execution bound for application-owned provider calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

Result = TypeVar("Result")


async def await_provider_call(
    operation: Awaitable[Result],
    *,
    timeout_seconds: float,
) -> Result:
    """Await one provider operation within the configured application bound.

    ``asyncio.timeout`` cancels the provider operation when this application's
    deadline expires while preserving an external task cancellation as
    ``CancelledError``. Provider adapters intentionally do not translate either
    signal into a model-visible response.
    """

    async with asyncio.timeout(timeout_seconds):
        return await operation
