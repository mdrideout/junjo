"""Dependency-free RFC 8785 JSON canonicalization for contract validation.

This implementation is adapted from Trail of Bits' ``rfc8785.py`` and
Andrew Rundgren's JSON Canonicalization Scheme reference implementation. Both
sources are licensed under the Apache License, Version 2.0:

* https://github.com/trailofbits/rfc8785.py
* https://github.com/cyberphone/json-canonicalization

Keeping the small implementation here lets the shared contract validator run
with the Python standard library while still checking the exact bytes used by
language SDK structural fingerprints.
"""

from __future__ import annotations

import math
import re
from io import BytesIO
from typing import Any, BinaryIO

_SAFE_INTEGER_MAX = 2**53 - 1
_SAFE_INTEGER_MIN = -_SAFE_INTEGER_MAX
_ESCAPE = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
for _codepoint in range(0x20):
    _ESCAPES.setdefault(chr(_codepoint), f"\\u{_codepoint:04x}")


class CanonicalizationError(ValueError):
    """Raised when a value is outside RFC 8785's I-JSON domain."""


def dumps(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 bytes for one JSON value."""

    sink = BytesIO()
    dump(value, sink)
    return sink.getvalue()


def dump(value: Any, sink: BinaryIO) -> None:
    """Write one RFC 8785 canonical JSON value to a binary sink."""

    if value is None:
        sink.write(b"null")
    elif isinstance(value, bool):
        sink.write(b"true" if value else b"false")
    elif isinstance(value, int):
        if not _SAFE_INTEGER_MIN <= value <= _SAFE_INTEGER_MAX:
            raise CanonicalizationError(
                f"integer {value} exceeds the interoperable IEEE-754 domain"
            )
        sink.write(str(value).encode("utf-8"))
    elif isinstance(value, float):
        _dump_float(value, sink)
    elif isinstance(value, str):
        _dump_string(value, sink)
    elif isinstance(value, (list, tuple)):
        sink.write(b"[")
        for index, item in enumerate(value):
            if index:
                sink.write(b",")
            dump(item, sink)
        sink.write(b"]")
    elif isinstance(value, dict):
        try:
            ordered = sorted(
                value.items(),
                key=lambda item: item[0].encode("utf-16be"),
            )
        except (AttributeError, UnicodeEncodeError) as error:
            raise CanonicalizationError(
                "object keys must be valid Unicode strings"
            ) from error
        sink.write(b"{")
        for index, (key, item) in enumerate(ordered):
            if not isinstance(key, str):
                raise CanonicalizationError("object keys must be strings")
            if index:
                sink.write(b",")
            _dump_string(key, sink)
            sink.write(b":")
            dump(item, sink)
        sink.write(b"}")
    else:
        raise CanonicalizationError(f"unsupported JSON value: {type(value).__name__}")


def _dump_string(value: str, sink: BinaryIO) -> None:
    def replace(match: re.Match[str]) -> str:
        return _ESCAPES[match.group(0)]

    sink.write(b'"')
    try:
        sink.write(_ESCAPE.sub(replace, value).encode("utf-8"))
    except UnicodeEncodeError as error:
        raise CanonicalizationError(
            "strings must not contain invalid Unicode surrogate code points"
        ) from error
    sink.write(b'"')


def _dump_float(value: float, sink: BinaryIO) -> None:
    if not math.isfinite(value):
        raise CanonicalizationError("NaN and infinity are not valid I-JSON numbers")
    if value == 0:
        sink.write(b"0")
        return
    if value < 0:
        sink.write(b"-")
        _dump_float(-value, sink)
        return

    text = str(value)
    exponent_text = ""
    exponent = 0
    exponent_index = text.find("e")
    if exponent_index > 0:
        exponent_text = text[exponent_index:]
        if exponent_text[2:3] == "0":
            exponent_text = exponent_text[:2] + exponent_text[3:]
        text = text[:exponent_index]
        exponent = int(exponent_text[1:])

    first = text
    dot = ""
    last = ""
    dot_index = text.find(".")
    if dot_index > 0:
        first = text[:dot_index]
        dot = "."
        last = text[dot_index + 1 :]
    if last == "0":
        dot = ""
        last = ""

    if 0 < exponent < 21:
        first += last
        last = ""
        dot = ""
        exponent_text = ""
        zero_count = exponent - len(first)
        while zero_count >= 0:
            first += "0"
            zero_count -= 1
    elif -7 < exponent < 0:
        last = first + last
        first = "0"
        dot = "."
        exponent_text = ""
        zero_count = exponent
        while zero_count < -1:
            last = "0" + last
            zero_count += 1

    sink.write(f"{first}{dot}{last}{exponent_text}".encode("utf-8"))
