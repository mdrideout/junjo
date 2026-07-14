"""Small cancellation boundary shared by executable terminal work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

TerminalT = TypeVar("TerminalT")


async def drain_terminal_work(
    work: Awaitable[TerminalT],
) -> tuple[TerminalT, asyncio.CancelledError | None]:
    """Finish one selected terminal transaction before returning cancellation.

    The caller task can be cancelled more than once while terminal work is in
    progress.  The owned child task is shielded until it is done, its result or
    exception is always retrieved, and the first caller cancellation is
    returned for propagation after the executable has committed its one
    selected outcome.
    """

    task = asyncio.ensure_future(work)
    remembered_cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as cancellation:
            if remembered_cancellation is None:
                remembered_cancellation = cancellation
    return task.result(), remembered_cancellation
