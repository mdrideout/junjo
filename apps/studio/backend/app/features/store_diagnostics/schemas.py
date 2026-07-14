"""Typed projections shared by Workflow and Agent Store diagnostics."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.features.telemetry_contract.types import (
    NonEmptyPortableText,
    SafeNonNegativeInt,
    SafePositiveInt,
)


class PayloadEvidence(BaseModel):
    """One emitted payload slot or explicit forensic absence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["full", "redacted", "excluded", "reference", "missing"]
    policy: NonEmptyPortableText | None = None
    value: Any | None = None
    reference: NonEmptyPortableText | None = None
    reason: NonEmptyPortableText | None = None

    @model_validator(mode="after")
    def validate_mode_shape(self) -> PayloadEvidence:
        """Keep absence, policy transformation, and JSON null unambiguous."""
        if self.mode == "missing":
            if any(value is not None for value in (self.policy, self.value, self.reference)):
                raise ValueError("missing evidence cannot contain policy, value, or reference")
            if not self.reason:
                raise ValueError("missing evidence requires a reason")
            return self

        if not self.policy:
            raise ValueError("emitted evidence requires a policy")
        if self.reason is not None:
            raise ValueError("emitted evidence cannot contain a missing-evidence reason")
        if self.mode == "reference":
            if not self.reference or self.value is not None:
                raise ValueError("reference evidence requires only a non-empty reference")
        elif self.mode == "excluded":
            if self.value is not None or self.reference is not None:
                raise ValueError("excluded evidence cannot contain a value or reference")
        elif self.reference is not None:
            raise ValueError("inline evidence cannot contain a reference")
        return self


class EvidenceDiagnostic(BaseModel):
    """Stable machine-readable evidence problem."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: NonEmptyPortableText
    path: NonEmptyPortableText
    message: NonEmptyPortableText


class EvidenceLossCounts(BaseModel):
    """Preserved OTLP loss counters relevant to one semantic projection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    resource_dropped_attributes: SafeNonNegativeInt
    span_dropped_attributes: SafeNonNegativeInt
    span_dropped_events: SafeNonNegativeInt
    span_dropped_links: SafeNonNegativeInt
    event_dropped_attributes: SafeNonNegativeInt


class EvidenceIntegrity(BaseModel):
    """Backend-owned verdict for required semantic evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["complete", "partial"]
    diagnostics: list[EvidenceDiagnostic]
    loss_counts: EvidenceLossCounts

    @model_validator(mode="after")
    def validate_status(self) -> EvidenceIntegrity:
        has_loss = any(value > 0 for value in self.loss_counts.model_dump().values())
        expected = "partial" if self.diagnostics or has_loss else "complete"
        if self.status != expected:
            raise ValueError("integrity status does not match diagnostics and loss counters")
        return self


class StoreTransition(BaseModel):
    """One ordered Store transition and its verified projections."""

    model_config = ConfigDict(extra="forbid", strict=True)

    sequence: SafePositiveInt
    revision_before: SafeNonNegativeInt
    revision_after: SafeNonNegativeInt
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    event_id: NonEmptyPortableText
    action: NonEmptyPortableText
    patch: PayloadEvidence
    before: Any | None = None
    after: Any | None = None

    @model_validator(mode="after")
    def validate_revision_step(self) -> StoreTransition:
        if self.revision_after not in {self.revision_before, self.revision_before + 1}:
            raise ValueError("transition revision must stay equal or increment by one")
        if not self.event_id or not self.action:
            raise ValueError("transition event ID and action must be non-empty")
        return self


class StoreDetail(BaseModel):
    """Owner-scoped Store evidence and the backend's reconstruction verdict."""

    model_config = ConfigDict(extra="forbid", strict=True)

    available: bool
    store_id: NonEmptyPortableText | None = None
    revision_start: SafeNonNegativeInt | None = None
    revision_end: SafeNonNegativeInt | None = None
    transition_count: SafeNonNegativeInt = 0
    reconstructable_claimed: bool = False
    reconstructable: bool
    reconstruction_status: Literal["verified", "policy_unavailable", "failed", "not_applicable"]
    reconstruction_reason: NonEmptyPortableText | None = None
    start: PayloadEvidence | None = None
    end: PayloadEvidence | None = None
    transitions: list[StoreTransition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability_shape(self) -> StoreDetail:
        if not self.available:
            if any(
                value is not None
                for value in (
                    self.store_id,
                    self.revision_start,
                    self.revision_end,
                    self.start,
                    self.end,
                )
            ):
                raise ValueError("unavailable Store cannot contain Store evidence")
            if self.transition_count or self.reconstructable_claimed or self.reconstructable:
                raise ValueError("unavailable Store cannot claim transitions or reconstruction")
            if self.transitions:
                raise ValueError("unavailable Store cannot contain transitions")
            if self.reconstruction_status != "not_applicable" or not self.reconstruction_reason:
                raise ValueError(
                    "unavailable Store requires a not-applicable reconstruction reason"
                )
            return self

        if self.reconstructable:
            if not self.store_id or self.revision_start is None or self.revision_end is None:
                raise ValueError(
                    "verified reconstruction requires complete Store identity and revisions"
                )
            if self.start is None or self.end is None:
                raise ValueError("verified reconstruction requires start and end evidence")
            if self.transition_count != len(self.transitions):
                raise ValueError("verified reconstruction requires every transition")
        expected_status = "verified" if self.reconstructable else self.reconstruction_status
        if self.reconstructable and expected_status != self.reconstruction_status:
            raise ValueError("reconstructable Store requires verified status")
        if self.reconstruction_status == "verified" and not self.reconstructable:
            raise ValueError("verified status requires reconstructability")
        if self.reconstruction_status == "not_applicable":
            raise ValueError("available Store cannot be not-applicable")
        if self.reconstruction_status == "verified":
            if self.reconstruction_reason is not None:
                raise ValueError("verified reconstruction cannot have an unavailability reason")
        elif not self.reconstruction_reason:
            raise ValueError("unverified reconstruction requires a reason")
        return self
