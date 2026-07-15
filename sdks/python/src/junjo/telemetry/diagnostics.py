"""Portable, non-throwing projections for runtime diagnostic text."""

from __future__ import annotations

import asyncio
import traceback

_UNAVAILABLE_MESSAGE = "<exception message unavailable>"
_UNAVAILABLE_STACKTRACE = "<exception stacktrace unavailable>"


def portable_diagnostic_text(
    value: object,
    *,
    fallback: str,
    nonempty: bool = False,
) -> str:
    """Project arbitrary diagnostic input into interoperable Unicode text.

    Diagnostic values are not application data boundaries: a broken
    ``__str__`` implementation must not replace the execution outcome Junjo
    has already selected.  Lone Unicode surrogates are replaced explicitly so
    every returned value can be encoded as strict UTF-8.
    """

    try:
        text = value if isinstance(value, str) else str(value)
        if nonempty and not text:
            return fallback
        return "".join("\N{REPLACEMENT CHARACTER}" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)
    except BaseException:
        return fallback


def exception_message(exc: BaseException) -> str:
    """Return non-throwing portable text for an exception message."""

    return portable_diagnostic_text(exc, fallback=_UNAVAILABLE_MESSAGE)


def error_type(exc: BaseException) -> str:
    """Return a portable, non-empty short exception type name."""

    return _text_attribute(
        type(exc),
        "__name__",
        fallback="BaseException",
        nonempty=True,
    )


def exception_event_type(exc: BaseException) -> str:
    """Return the qualified type used by standard OpenTelemetry events."""

    exception_class = type(exc)
    short_name = error_type(exc)
    qualname = _text_attribute(
        exception_class,
        "__qualname__",
        fallback=short_name,
        nonempty=True,
    )
    if qualname.rsplit(".", 1)[-1] != short_name:
        qualname = short_name
    module = _text_attribute(exception_class, "__module__", fallback="")
    if module and module != "builtins":
        return f"{module}.{qualname}"
    return qualname


def exception_stacktrace(exc: BaseException) -> str:
    """Return a portable traceback without trusting exception formatting."""

    try:
        stacktrace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except BaseException:
        return _UNAVAILABLE_STACKTRACE
    return portable_diagnostic_text(
        stacktrace,
        fallback=_UNAVAILABLE_STACKTRACE,
    )


def cancellation_reason(exc: asyncio.CancelledError) -> str:
    """Return a portable cancellation reason without changing propagation."""

    try:
        arguments = exc.args
        if not arguments:
            return "cancelled"
        reason = arguments[0]
    except BaseException:
        return "cancelled"
    return portable_diagnostic_text(
        reason,
        fallback="cancelled",
        nonempty=True,
    )


def callable_identity(callback: object) -> str:
    """Return a best-effort portable identity for a lifecycle callback."""

    callback_type = type(callback)
    module = _text_attribute(callback, "__module__", fallback="") or _text_attribute(
        callback_type,
        "__module__",
        fallback="unknown",
    )
    name = _text_attribute(callback, "__qualname__", fallback="")
    if not name:
        name = _text_attribute(callback, "__name__", fallback="")
    if not name:
        name = _text_attribute(callback_type, "__qualname__", fallback="callable")
    return portable_diagnostic_text(
        f"{module}.{name}",
        fallback="unknown.callable",
        nonempty=True,
    )


def _text_attribute(
    owner: object,
    name: str,
    *,
    fallback: str,
    nonempty: bool = False,
) -> str:
    try:
        value = getattr(owner, name)
        if not isinstance(value, str):
            return fallback
    except BaseException:
        return fallback
    return portable_diagnostic_text(
        value,
        fallback=fallback,
        nonempty=nonempty,
    )
