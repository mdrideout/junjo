import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from opentelemetry import trace

tracer = trace.get_tracer(__name__)


async def _instrumented_task_wrapper(
    span_name: str,
    target_func: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
):
    """
    An internal wrapper for a task to manage the span's lifecycle.
    """
    with tracer.start_as_current_span(span_name) as span:
        # If the first argument has a 'chat_id', add it as an attribute.
        if args and hasattr(args, "chat_id"):
            span.set_attribute("chat_id", args[0].chat_id)
        await target_func(*args, **kwargs)


def otel_wrap_background_task(
    target_func: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
):
    """
    Creates and schedules an instrumented background task.

    This function wraps the target async function in a new OpenTelemetry span
    and schedules it to run as a background task using asyncio.create_task.

    :param span_name: The name for the new OpenTelemetry span.
    :param target_func: The async function to execute.
    :param args: Positional arguments to pass to the target function.
    :param kwargs: Keyword arguments to pass to the target function.
    """
    asyncio.create_task(
        _instrumented_task_wrapper("background_task", target_func, *args, **kwargs)
    )
