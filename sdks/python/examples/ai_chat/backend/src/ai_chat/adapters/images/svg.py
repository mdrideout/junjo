"""Credential-free SVG artifact rendering for the runnable example."""

from __future__ import annotations

import hashlib
import html
import textwrap
from pathlib import Path

from ai_chat.domain.models import ImageArtifact
from ai_chat.domain.ports import IdFactory


class SvgImageRenderer:
    """Write one small deterministic SVG file per explicit image request."""

    def __init__(self, *, directory: Path, id_factory: IdFactory) -> None:
        self.directory = directory
        self._id_factory = id_factory
        self.directory.mkdir(parents=True, exist_ok=True)

    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        artifact_id = self._id_factory()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        color_one = f"#{digest[:6]}"
        color_two = f"#{digest[6:12]}"
        lines = textwrap.wrap(prompt, width=36)[:6]
        text = "".join(
            f'<text x="320" y="{250 + index * 34}" text-anchor="middle">{html.escape(line)}</text>'
            for index, line in enumerate(lines)
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" '
            'viewBox="0 0 640 640">'
            '<defs><linearGradient id="background" x2="1" y2="1">'
            f'<stop stop-color="{color_one}"/><stop offset="1" stop-color="{color_two}"/>'
            "</linearGradient></defs>"
            '<rect width="640" height="640" fill="url(#background)"/>'
            '<g fill="white" font-family="system-ui, sans-serif" font-size="24">'
            f"{text}</g></svg>"
        )
        (self.directory / f"{artifact_id}.svg").write_text(svg, encoding="utf-8")
        return ImageArtifact(
            id=artifact_id,
            url=f"/api/images/{artifact_id}.svg",
            alt_text=alt_text,
        )
