"""Run the mixed OpenAI Agents and Junjo application once."""

from __future__ import annotations

import asyncio

from agents import Runner

from .application import build_openai_agent
from .telemetry import start_telemetry


async def _run() -> None:
    telemetry = start_telemetry()
    try:
        result = await Runner.run(
            build_openai_agent(),
            "Recommend a realistic local place for a weekend afternoon.",
        )
        print(result.final_output)
    finally:
        telemetry.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
