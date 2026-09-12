"""Canonical metadata and rendering for the installed evaluation CLI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, JsonValue

DEFAULT_STUDIO_BACKEND_BASE_URL = "http://localhost:26154"


@dataclass(frozen=True, slots=True)
class CommandMetadata:
    """Canonical machine- and human-readable description of one leaf command."""

    path: str
    summary: str
    authentication: str
    harness: str
    executes_evaluation_target: bool
    response: str
    evidence_level: str | None = None


class CliInterfaceDto(BaseModel):
    """Closed immutable contract used by the CLI explainer."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfigurationMetadata(CliInterfaceDto):
    """Canonical description of one CLI configuration input."""

    name: str
    flag: str | None
    environment: str | None
    pyproject: str | None
    default: str | None
    purpose: str


class EvidenceAccessMetadata(CliInterfaceDto):
    """One explicit evidence hydration level."""

    name: str
    command: str
    description: str


class CommandArgumentMetadata(CliInterfaceDto):
    """One argument projected directly from its argparse action."""

    name: str
    flags: tuple[str, ...]
    required: bool
    repeatable: bool
    description: str
    choices: JsonValue | None = None
    default: JsonValue | None = None


class ExplainedCommand(CliInterfaceDto):
    """Machine- and human-readable interface facts for one leaf command."""

    command: str
    summary: str
    authentication: str
    harness: str
    executes_evaluation_target: bool
    response: str
    evidence_level: str | None
    arguments: tuple[CommandArgumentMetadata, ...]


class EvaluationCliInterface(CliInterfaceDto):
    """Complete local reference for the installed evaluation CLI version."""

    interface_version: int
    purpose: str
    agent_guidance: dict[str, str]
    configuration: tuple[ConfigurationMetadata, ...]
    evidence_access: tuple[EvidenceAccessMetadata, ...]
    commands: tuple[ExplainedCommand, ...]
    output: dict[str, str]


EVALUATION_CONFIG = (
    ConfigurationMetadata(
        name="Evaluation harness",
        flag="--harness module:object",
        environment=None,
        pyproject="[tool.junjo.evaluation].harness",
        default=None,
        purpose=(
            "Imports the application-owned EvaluationHarness that declares targets, "
            "evaluators, runtime resources, and service identity."
        ),
    ),
    ConfigurationMetadata(
        name="Studio backend base URL",
        flag="--studio-backend-base-url URL",
        environment="JUNJO_AI_STUDIO_BACKEND_BASE_URL",
        pyproject=None,
        default=DEFAULT_STUDIO_BACKEND_BASE_URL,
        purpose="Selects the Junjo AI Studio control/query API origin.",
    ),
    ConfigurationMetadata(
        name="Developer access token",
        flag=None,
        environment="JUNJO_AI_STUDIO_CLI_TOKEN",
        pyproject=None,
        default=None,
        purpose=(
            "Authenticates evaluation control and evidence queries. This is separate "
            "from JUNJO_AI_STUDIO_API_KEY, which applications use only for OTLP telemetry ingestion."
        ),
    ),
)

EVIDENCE_ACCESS_LEVELS = (
    EvidenceAccessMetadata(
        name="attempt_summary",
        command="junjo eval attempt get --attempt-id ATTEMPT_ID",
        description="Bounded evaluation, Case, target, result, and evidence-binding context.",
    ),
    EvidenceAccessMetadata(
        name="manifest",
        command="junjo eval attempt evidence manifest --attempt-id ATTEMPT_ID",
        description="Bounded trace structure, failures, operations, Store integrity, and selectable span IDs.",
    ),
    EvidenceAccessMetadata(
        name="selected_spans",
        command=("junjo eval attempt evidence spans --attempt-id ATTEMPT_ID --span-id SPAN_ID [--span-id SPAN_ID ...]"),
        description="Complete evidence for an explicit set of spans from the attempt trace.",
    ),
    EvidenceAccessMetadata(
        name="full",
        command="junjo eval attempt evidence full --attempt-id ATTEMPT_ID",
        description="Complete lossless trace evidence and every semantic annotation.",
    ),
)


def build_evaluation_interface(parser: argparse.ArgumentParser) -> EvaluationCliInterface:
    """Project the parser's canonical leaf metadata into an explainer contract."""

    commands: list[ExplainedCommand] = []
    for command_parser, metadata in _leaf_commands(parser):
        arguments: list[CommandArgumentMetadata] = []
        for action in command_parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            choices: JsonValue | None = None
            if isinstance(action.choices, range):
                choices = {
                    "minimum": action.choices.start,
                    "maximum": action.choices.stop - 1,
                }
            elif action.choices is not None:
                choices = list(action.choices)
            default: JsonValue | None = None
            if action.default is not None and action.default is not argparse.SUPPRESS:
                default = action.default
            arguments.append(
                CommandArgumentMetadata(
                    name=action.dest,
                    flags=tuple(action.option_strings),
                    required=action.required,
                    repeatable=isinstance(action, argparse._AppendAction),
                    description=action.help or "",
                    choices=choices,
                    default=default,
                )
            )
        commands.append(
            ExplainedCommand(
                command=f"junjo {metadata.path.replace('.', ' ')}",
                summary=metadata.summary,
                authentication=metadata.authentication,
                harness=metadata.harness,
                executes_evaluation_target=metadata.executes_evaluation_target,
                response=metadata.response,
                evidence_level=metadata.evidence_level,
                arguments=tuple(arguments),
            )
        )
    return EvaluationCliInterface(
        interface_version=1,
        purpose=(
            "Build Studio-backed datasets, execute application targets, compare binary "
            "outcomes, and hydrate exact execution evidence."
        ),
        agent_guidance={
            "skill_name": "junjo-evaluation",
            "discovery_command": "junjo eval skill path",
            "responsibility": (
                "The installed skill explains evaluation workflow and judgment design; "
                "this interface reference explains commands and configuration."
            ),
        },
        configuration=EVALUATION_CONFIG,
        evidence_access=EVIDENCE_ACCESS_LEVELS,
        commands=tuple(commands),
        output={
            "data_commands": ("One JSON envelope containing schema_version, ok, command, and either data or error."),
            "explain_default": "Markdown written to standard output.",
            "explain_json": "The normal JSON envelope containing this EvaluationCliInterface object.",
        },
    )


def _leaf_commands(
    parser: argparse.ArgumentParser,
) -> list[tuple[argparse.ArgumentParser, CommandMetadata]]:
    leaves: list[tuple[argparse.ArgumentParser, CommandMetadata]] = []
    metadata = parser.get_default("_command_metadata")
    if isinstance(metadata, CommandMetadata):
        leaves.append((parser, metadata))
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for child in action.choices.values():
            leaves.extend(_leaf_commands(child))
    return leaves


def render_evaluation_interface_markdown(interface: EvaluationCliInterface) -> str:
    """Render the validated interface contract as readable local Markdown."""

    lines = [
        "# Junjo Evaluation CLI",
        "",
        interface.purpose,
        "",
        "Data commands return one machine-readable JSON envelope. Use the installed "
        "`junjo-evaluation` skill for workflow and evaluator-design guidance.",
        "",
        "## Configuration",
        "",
    ]
    for item in interface.configuration:
        sources = [value for value in (item.flag, item.environment, item.pyproject) if value is not None]
        if item.default is not None:
            sources.append(f"default: {item.default}")
        source_text = "`, `".join(sources)
        lines.extend(
            [
                f"### {item.name}",
                "",
                item.purpose,
                "",
                f"Sources, highest precedence first: `{source_text}`.",
                "",
            ]
        )

    lines.extend(["## Evidence access", ""])
    for level in interface.evidence_access:
        lines.extend(
            [
                f"- `{level.name}` — `{level.command}`",
                f"  {level.description}",
            ]
        )

    lines.extend(["", "## Commands", ""])
    for command in interface.commands:
        lines.extend(
            [
                f"### `{command.command}`",
                "",
                command.summary,
                "",
                f"- Authentication: `{command.authentication}`",
                f"- Evaluation harness: `{command.harness}`",
                f"- Executes an evaluation target: `{'yes' if command.executes_evaluation_target else 'no'}`",
                f"- Response: `{command.response}`",
            ]
        )
        if command.evidence_level is not None:
            lines.append(f"- Evidence level: `{command.evidence_level}`")
        if command.arguments:
            lines.extend(["", "Arguments:", ""])
            for argument in command.arguments:
                flag = ", ".join(argument.flags) or argument.name
                qualities = []
                if argument.required:
                    qualities.append("required")
                if argument.repeatable:
                    qualities.append("repeatable")
                suffix = f" ({', '.join(qualities)})" if qualities else ""
                lines.append(f"- `{flag}`{suffix}: {argument.description}")
        lines.append("")
    return "\n".join(lines).rstrip()
