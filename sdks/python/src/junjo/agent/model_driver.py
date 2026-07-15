"""Provider-neutral ModelDriver contracts and immutable binding declarations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .._json import (
    JsonBoundaryError,
    freeze_json,
    require_ijson_text,
    thaw_json,
)
from .errors import ModelDriverConfigurationError
from .json import FrozenJsonValue
from .messages import ModelRequest


class ModelDriver(Protocol):
    """Translate one normalized Junjo request into one normalized response."""

    async def request(self, request: ModelRequest) -> object:
        """Perform one provider operation and return a normalized response candidate."""


ModelDriverFactory = Callable[[], ModelDriver]


@dataclass(frozen=True, slots=True, init=False)
class ModelDriverDescriptor:
    """Immutable, credential-free identity for one ModelDriver binding."""

    driver_key: str
    provider: str
    model: str
    settings: Mapping[str, FrozenJsonValue]

    def __init__(
        self,
        *,
        driver_key: str,
        provider: str,
        model: str,
        settings: Mapping[str, object] | None = None,
    ) -> None:
        """Create credential-free model identity used in evidence and hashes.

        :param driver_key: Stable adapter implementation key.
        :param provider: Provider identity such as ``openai`` or ``junjo``.
        :param model: Provider model identity.
        :param settings: Portable behavior-affecting settings. Credentials and
            runtime clients do not belong here.
        :raises ModelDriverConfigurationError: If identity or settings are not
            portable I-JSON.
        """
        for field, value in (
            ("driver_key", driver_key),
            ("provider", provider),
            ("model", model),
        ):
            try:
                require_ijson_text(value, field, nonempty=True)
            except JsonBoundaryError as exc:
                raise ModelDriverConfigurationError(str(exc)) from exc
            object.__setattr__(self, field, value)
        try:
            frozen_settings = freeze_json(settings or {})
        except Exception as exc:
            raise ModelDriverConfigurationError(
                "ModelDriver settings must be JSON-compatible."
            ) from exc
        if not isinstance(frozen_settings, Mapping):
            raise ModelDriverConfigurationError("ModelDriver settings must be a JSON object.")
        object.__setattr__(self, "settings", frozen_settings)

    def to_json(self) -> dict[str, object]:
        return {
            "driverKey": self.driver_key,
            "provider": self.provider,
            "model": self.model,
            "settings": thaw_json(self.settings),
        }


@dataclass(frozen=True, slots=True, init=False)
class ModelDriverBinding:
    """Bind a descriptor to exactly one shared driver or per-run factory."""

    descriptor: ModelDriverDescriptor
    shared_driver: ModelDriver | None
    factory: ModelDriverFactory | None

    def __init__(
        self,
        *,
        descriptor: ModelDriverDescriptor,
        shared_driver: ModelDriver | None = None,
        factory: ModelDriverFactory | None = None,
    ) -> None:
        """Bind a descriptor to one explicit driver lifecycle.

        :param descriptor: Credential-free evidence identity.
        :param shared_driver: Caller-owned concurrency-safe driver instance.
        :param factory: Synchronous factory producing a fresh driver per run.
        :raises ModelDriverConfigurationError: If exactly one ownership mode
            is not declared.
        """
        if (shared_driver is None) == (factory is None):
            raise ModelDriverConfigurationError(
                "ModelDriverBinding requires exactly one shared_driver or factory."
            )
        if not isinstance(descriptor, ModelDriverDescriptor):
            raise ModelDriverConfigurationError("descriptor must be a ModelDriverDescriptor.")
        if shared_driver is not None and not callable(getattr(shared_driver, "request", None)):
            raise ModelDriverConfigurationError("shared_driver must implement async request().")
        if factory is not None and not callable(factory):
            raise ModelDriverConfigurationError("factory must be callable.")
        object.__setattr__(self, "descriptor", descriptor)
        object.__setattr__(self, "shared_driver", shared_driver)
        object.__setattr__(self, "factory", factory)

    @classmethod
    def shared(
        cls,
        *,
        descriptor: ModelDriverDescriptor,
        driver: ModelDriver,
    ) -> ModelDriverBinding:
        """Declare a caller-guaranteed concurrent-safe shared driver."""

        return cls(descriptor=descriptor, shared_driver=driver)

    @classmethod
    def per_run(
        cls,
        *,
        descriptor: ModelDriverDescriptor,
        factory: ModelDriverFactory,
    ) -> ModelDriverBinding:
        """Declare a lazy, synchronous per-run driver factory."""

        return cls(descriptor=descriptor, factory=factory)
