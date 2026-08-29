"""Bounded asynchronous client for Junjo AI Studio evaluation APIs."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError

from .comparison import RunComparison, project_run_comparison
from .errors import (
    AttemptEvidenceUnavailable,
    ExecutionEvidencePending,
    ExecutionIdentityAmbiguous,
    StudioAuthenticationError,
    StudioAuthorizationError,
    StudioConflictError,
    StudioContractError,
    StudioRequestError,
    StudioResponseTooLargeError,
    StudioTransientError,
    StudioValidationError,
)
from .models import (
    MAX_PAGE_SIZE,
    AttemptDetail,
    AttemptEvidence,
    AttemptEvidenceBind,
    AttemptEvidenceManifest,
    AttemptEvidenceSpanRequest,
    AttemptEvidenceSpans,
    AttemptRead,
    AttemptResultWrite,
    CaseCreate,
    CaseRead,
    ConflictResponse,
    CursorText,
    DatasetCreate,
    DatasetDetail,
    DatasetList,
    DatasetRead,
    EvidenceMembershipList,
    ExecutionEvidenceReference,
    ExecutionResolutionConflict,
    ExecutionResolutionRead,
    KeyText,
    OpenTelemetrySpanResolutionRead,
    RecordId,
    RunDetail,
    RunList,
    RunScope,
    RunStart,
    SemanticExecutionReference,
    StudioHealth,
    TargetKind,
    TraceEvidenceRead,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_CONTROL_RESPONSE_BYTES = 8 * 1024 * 1024
_DEFAULT_EVIDENCE_RESPONSE_BYTES = 32 * 1024 * 1024
_TRACE_ID = TypeAdapter(str)
_RECORD_ID = TypeAdapter(RecordId)
_KEY_TEXT = TypeAdapter(KeyText)
_CURSOR_TEXT = TypeAdapter(CursorText)


@dataclass(frozen=True, slots=True)
class _BufferedResponse:
    status_code: int
    content: bytes


class StudioClient:
    """One pooled, bounded Studio control/query client.

    Evaluation operations use a separately scoped Studio control/query token.
    Ingestion API keys and Studio account passwords are not accepted by this
    interface. A token may be omitted only for unauthenticated capability and
    health inspection.

    The client reuses one :class:`httpx.AsyncClient` for its lifetime.  It
    applies explicit connection and timeout limits, consumes response streams
    under byte budgets, and retries only transport failures or transient HTTP
    statuses. Evaluation mutations are idempotently keyed by their explicit
    Studio natural keys, so every retry sends the exact same payload.

    :param base_url: Studio origin, such as ``https://studio.example.com``.
        Plain HTTP is accepted only for a loopback origin.
    :param token: Scoped Studio control/query token.  It is sent as a Bearer
        token and is redacted from object representations and errors.
    :param connect_timeout_seconds: Maximum connection-establishment time.
    :param read_timeout_seconds: Maximum wait for each response read.
    :param write_timeout_seconds: Maximum wait for request writes.
    :param pool_timeout_seconds: Maximum wait for a pooled connection.
    :param max_connections: Upper bound for all pooled connections.
    :param max_keepalive_connections: Upper bound for idle pooled connections.
    :param retry_attempts: Total attempts for retryable requests, including the
        first attempt.
    :param retry_backoff_seconds: Initial non-blocking exponential backoff.
    :param max_control_response_bytes: Byte budget for control API responses.
    :param max_evidence_response_bytes: Byte budget used for explicitly
        selected spans or complete trace evidence.
    :param transport: Optional HTTPX transport, primarily for deterministic
        tests or an explicitly managed application transport.
    """

    _EVALUATION_PREFIX = "/api/v1/evaluation"

    def __init__(
        self,
        *,
        base_url: str,
        token: str | SecretStr | None = None,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        write_timeout_seconds: float = 30.0,
        pool_timeout_seconds: float = 5.0,
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.25,
        max_control_response_bytes: int = _DEFAULT_CONTROL_RESPONSE_BYTES,
        max_evidence_response_bytes: int = _DEFAULT_EVIDENCE_RESPONSE_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_base_url = _validate_base_url(base_url)
        secret = _validate_token(token)
        _require_positive_float("connect_timeout_seconds", connect_timeout_seconds)
        _require_positive_float("read_timeout_seconds", read_timeout_seconds)
        _require_positive_float("write_timeout_seconds", write_timeout_seconds)
        _require_positive_float("pool_timeout_seconds", pool_timeout_seconds)
        if not 1 <= max_connections <= 100:
            raise ValueError("max_connections must be between 1 and 100.")
        if not 0 <= max_keepalive_connections <= max_connections:
            raise ValueError("max_keepalive_connections must be between 0 and max_connections.")
        if not 1 <= retry_attempts <= 5:
            raise ValueError("retry_attempts must be between 1 and 5.")
        if retry_backoff_seconds < 0 or retry_backoff_seconds > 10:
            raise ValueError("retry_backoff_seconds must be between 0 and 10.")
        _require_response_bound("max_control_response_bytes", max_control_response_bytes)
        _require_response_bound("max_evidence_response_bytes", max_evidence_response_bytes)

        self._base_url = normalized_base_url
        self._token = secret
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._max_control_response_bytes = max_control_response_bytes
        self._max_evidence_response_bytes = max_evidence_response_bytes

        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "junjo-python-studio-client",
        }
        if secret is not None:
            headers["Authorization"] = f"Bearer {secret.get_secret_value()}"

        self._http = httpx.AsyncClient(
            base_url=normalized_base_url,
            headers=headers,
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=write_timeout_seconds,
                pool=pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
                keepalive_expiry=30.0,
            ),
            transport=transport,
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        """Return configuration identity without exposing credentials."""

        token = "[redacted]" if self._token is not None else None
        return f"{type(self).__name__}(base_url={self._base_url!r}, token={token!r})"

    async def __aenter__(self) -> StudioClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close pooled connections."""

        await self._http.aclose()

    async def get_health(self) -> StudioHealth:
        """Return Studio status and product version through bounded transport."""

        return await self._model_request(
            "GET",
            "/health",
            StudioHealth,
        )

    async def create_dataset(self, request: DatasetCreate) -> DatasetRead:
        """Create or retrieve a dataset by application key and dataset key."""

        path = f"{self._EVALUATION_PREFIX}/datasets"
        return await self._model_request(
            "POST",
            path,
            DatasetRead,
            json=request.model_dump(mode="json"),
        )

    async def list_datasets(
        self,
        *,
        application_key: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> DatasetList:
        """Return one bounded cursor page of datasets.

        The method intentionally returns one page rather than silently
        hydrating an unbounded collection.  Callers must explicitly continue
        with ``next_cursor``.
        """

        if application_key is not None:
            application_key = _KEY_TEXT.validate_python(application_key, strict=True)
        cursor = _validated_cursor(cursor)
        _require_page_limit(limit)
        params: dict[str, str | int] = {"limit": limit}
        if application_key is not None:
            params["application_key"] = application_key
        if cursor is not None:
            params["cursor"] = cursor
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/datasets",
            DatasetList,
            params=params,
        )

    async def get_dataset(self, dataset_id: str) -> DatasetDetail:
        """Return a dataset and its complete bounded case membership."""

        dataset_id = _validated_record_id(dataset_id)
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/datasets/{_path_segment(dataset_id)}",
            DatasetDetail,
        )

    async def add_case(self, dataset_id: str, request: CaseCreate) -> CaseRead:
        """Append or retrieve one idempotently keyed case in a draft dataset."""

        dataset_id = _validated_record_id(dataset_id)
        path = f"{self._EVALUATION_PREFIX}/datasets/{_path_segment(dataset_id)}/cases"
        return await self._model_request(
            "POST",
            path,
            CaseRead,
            json=request.model_dump(mode="json"),
        )

    async def lock_dataset(self, dataset_id: str) -> DatasetRead:
        """Idempotently lock one dataset against further case changes."""

        dataset_id = _validated_record_id(dataset_id)
        path = f"{self._EVALUATION_PREFIX}/datasets/{_path_segment(dataset_id)}/lock"
        return await self._model_request(
            "PUT",
            path,
            DatasetRead,
        )

    async def start_run(self, request: RunStart) -> RunDetail:
        """Create or retrieve a run by dataset and stable request key."""

        path = f"{self._EVALUATION_PREFIX}/runs"
        return await self._model_request(
            "POST",
            path,
            RunDetail,
            json=request.model_dump(mode="json"),
        )

    async def list_runs(
        self,
        *,
        dataset_id: str | None = None,
        target_kind: TargetKind | None = None,
        target_key: str | None = None,
        input_version: int | None = None,
        evaluation_name: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> RunList:
        """Return one bounded page scoped by conjunctive case identity filters."""

        scope = RunScope(
            dataset_id=dataset_id,
            target_kind=target_kind,
            target_key=target_key,
            input_version=input_version,
            evaluation_name=evaluation_name,
        )
        cursor = _validated_cursor(cursor)
        _require_page_limit(limit)
        params: dict[str, str | int] = {"limit": limit}
        for key, value in scope.model_dump(mode="json", exclude_none=True).items():
            params[key] = value
        if cursor is not None:
            params["cursor"] = cursor
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/runs",
            RunList,
            params=params,
        )

    async def get_run(self, run_id: str) -> RunDetail:
        """Return one run and its exact case-attempt membership."""

        run_id = _validated_record_id(run_id)
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/runs/{_path_segment(run_id)}",
            RunDetail,
        )

    async def compare_runs(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
        *,
        target_kind: TargetKind | None = None,
        target_key: str | None = None,
        input_version: int | None = None,
        evaluation_name: str | None = None,
    ) -> RunComparison:
        """Fetch and compare two runs without hydrating full trace evidence."""

        baseline = await self.get_run(baseline_run_id)
        candidate = await self.get_run(candidate_run_id)
        return project_run_comparison(
            baseline,
            candidate,
            scope=RunScope(
                target_kind=target_kind,
                target_key=target_key,
                input_version=input_version,
                evaluation_name=evaluation_name,
            ),
        )

    async def get_attempt(self, attempt_id: str) -> AttemptDetail:
        """Return one attempt with its run, dataset, and case context."""

        attempt_id = _validated_record_id(attempt_id)
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/attempts/{_path_segment(attempt_id)}",
            AttemptDetail,
        )

    async def bind_attempt_evidence(
        self,
        attempt_id: str,
        evidence: ExecutionEvidenceReference,
    ) -> AttemptRead:
        """Idempotently bind exact execution evidence to an attempt."""

        attempt_id = _validated_record_id(attempt_id)
        request = AttemptEvidenceBind(evidence=evidence)
        path = f"{self._EVALUATION_PREFIX}/attempts/{_path_segment(attempt_id)}/evidence"
        return await self._model_request(
            "PUT",
            path,
            AttemptRead,
            json=request.model_dump(mode="json"),
        )

    async def record_attempt_result(
        self,
        attempt_id: str,
        result: AttemptResultWrite,
    ) -> AttemptRead:
        """Idempotently record one terminal evaluation judgment."""

        attempt_id = _validated_record_id(attempt_id)
        path = f"{self._EVALUATION_PREFIX}/attempts/{_path_segment(attempt_id)}/result"
        return await self._model_request(
            "PUT",
            path,
            AttemptRead,
            json=result.model_dump(mode="json"),
        )

    async def resolve_execution(
        self,
        execution: SemanticExecutionReference,
    ) -> ExecutionResolutionRead:
        """Resolve exact semantic identity to a received Studio owner span.

        :raises ExecutionEvidencePending: When Studio has not indexed the
            execution.
        :raises ExecutionIdentityAmbiguous: When identity matches more than
            one owner span.
        """

        path = "/api/v1/execution-resolution"
        response = await self._request(
            "GET",
            path,
            params={
                "service_namespace": execution.service_namespace,
                "service_name": execution.service_name,
                "executable_type": execution.executable_type.value,
                "runtime_id": execution.runtime_id,
            },
            max_response_bytes=self._max_control_response_bytes,
        )
        if response.status_code == 404:
            raise ExecutionEvidencePending(execution)
        if response.status_code == 409:
            conflict = self._parse(response, ExecutionResolutionConflict)
            raise ExecutionIdentityAmbiguous(execution, conflict)
        self._raise_for_status(response, method="GET", path=path)
        return self._parse(response, ExecutionResolutionRead)

    async def get_trace_evidence(self, trace_id: str) -> TraceEvidenceRead:
        """Explicitly hydrate complete evidence for one trace.

        Complete trace and selected-span operations use the larger evidence
        byte budget. Listing, detail, comparison, manifest, and membership
        operations remain bounded control projections.
        """

        trace_id = _validate_trace_id(trace_id)
        path = f"/api/v1/trace-evidence/{trace_id}"
        response = await self._request(
            "GET",
            path,
            max_response_bytes=self._max_evidence_response_bytes,
        )
        self._raise_for_status(response, method="GET", path=path)
        return self._parse(response, TraceEvidenceRead)

    async def get_attempt_evidence(self, attempt_id: str) -> AttemptEvidence:
        """Join an attempt to its exact complete Studio trace evidence."""

        attempt, subject_evidence = await self._get_attempt_subject(attempt_id)
        if isinstance(subject_evidence, SemanticExecutionReference):
            resolution: ExecutionResolutionRead | OpenTelemetrySpanResolutionRead = await self.resolve_execution(
                subject_evidence
            )
        else:
            encoded_service_name = quote(subject_evidence.service_name, safe="")
            trace_path = f"/traces/{encoded_service_name}/{subject_evidence.trace_id}/{subject_evidence.span_id}"
            resolution = OpenTelemetrySpanResolutionRead(
                service_namespace=subject_evidence.service_namespace,
                service_name=subject_evidence.service_name,
                trace_id=subject_evidence.trace_id,
                span_id=subject_evidence.span_id,
                detail_path=trace_path,
                trace_path=trace_path,
            )
        try:
            evidence = await self.get_trace_evidence(resolution.trace_id)
        except StudioRequestError as error:
            if error.status_code == 404:
                raise ExecutionEvidencePending(subject_evidence) from error
            raise
        return AttemptEvidence(
            attempt=attempt,
            resolution=resolution,
            evidence=evidence,
        )

    async def get_attempt_evidence_manifest(
        self,
        attempt_id: str,
    ) -> AttemptEvidenceManifest:
        """Return bounded trace structure and selectable identities for an Attempt.

        This is the normal first evidence query after inspecting the Attempt
        control record. Full prompts, responses, state, events, and stack traces
        remain available through selected-span or complete-trace hydration.

        :param attempt_id: Studio evaluation Attempt record ID.
        :return: Bounded subject, trace, failure, executable, operation, Store,
            relationship, and diagnostic summaries.
        :raises AttemptEvidenceUnavailable: If the Attempt has no evidence binding.
        :raises ExecutionEvidencePending: If Studio has not indexed the bound
            trace evidence yet.
        :raises ExecutionIdentityAmbiguous: If the semantic execution identity
            resolves to more than one owner span.
        """

        attempt_id = _validated_record_id(attempt_id)
        _, subject_evidence = await self._get_attempt_subject(attempt_id)
        path = f"/api/v1/trace-evidence/attempts/{_path_segment(attempt_id)}/manifest"
        response = await self._request(
            "GET",
            path,
            max_response_bytes=self._max_control_response_bytes,
        )
        if response.status_code == 404:
            raise ExecutionEvidencePending(subject_evidence)
        if response.status_code == 409:
            conflict = self._parse(response, ExecutionResolutionConflict)
            if not isinstance(subject_evidence, SemanticExecutionReference):
                raise StudioContractError("Studio reported ambiguous semantic identity for exact span evidence.")
            raise ExecutionIdentityAmbiguous(subject_evidence, conflict)
        self._raise_for_status(response, method="GET", path=path)
        return self._parse(response, AttemptEvidenceManifest)

    async def get_attempt_evidence_spans(
        self,
        attempt_id: str,
        span_ids: Sequence[str],
    ) -> AttemptEvidenceSpans:
        """Return complete evidence for explicitly selected spans in one Attempt trace.

        Requested identities are kept in caller order. Studio returns identities
        absent from the bound trace in ``missing_span_ids`` rather than silently
        discarding them.

        :param attempt_id: Studio evaluation Attempt record ID.
        :param span_ids: Non-empty unique sequence of exact lowercase hexadecimal
            OpenTelemetry span IDs.
        :return: Complete raw spans with only their directly associated semantic
            annotations, plus explicit missing identities.
        :raises AttemptEvidenceUnavailable: If the Attempt has no evidence binding.
        :raises ExecutionEvidencePending: If Studio has not indexed the bound
            trace evidence yet.
        :raises ExecutionIdentityAmbiguous: If the semantic execution identity
            resolves to more than one owner span.
        """

        attempt_id = _validated_record_id(attempt_id)
        request = AttemptEvidenceSpanRequest(span_ids=tuple(span_ids))
        _, subject_evidence = await self._get_attempt_subject(attempt_id)
        path = f"/api/v1/trace-evidence/attempts/{_path_segment(attempt_id)}/spans"
        response = await self._request(
            "POST",
            path,
            json=request.model_dump(mode="json"),
            max_response_bytes=self._max_evidence_response_bytes,
        )
        if response.status_code == 404:
            raise ExecutionEvidencePending(subject_evidence)
        if response.status_code == 409:
            conflict = self._parse(response, ExecutionResolutionConflict)
            if not isinstance(subject_evidence, SemanticExecutionReference):
                raise StudioContractError("Studio reported ambiguous semantic identity for exact span evidence.")
            raise ExecutionIdentityAmbiguous(subject_evidence, conflict)
        self._raise_for_status(response, method="POST", path=path)
        return self._parse(response, AttemptEvidenceSpans)

    async def _get_attempt_subject(
        self,
        attempt_id: str,
    ) -> tuple[AttemptDetail, ExecutionEvidenceReference]:
        attempt = await self.get_attempt(attempt_id)
        subject_evidence = attempt.attempt.subject_evidence
        if subject_evidence is None:
            raise AttemptEvidenceUnavailable(attempt_id)
        return attempt, subject_evidence

    async def get_evidence_membership(
        self,
        evidence: ExecutionEvidenceReference,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> EvidenceMembershipList:
        """Return one bounded page of exact evaluation membership."""

        cursor = _validated_cursor(cursor)
        _require_page_limit(limit)
        params: dict[str, str | int] = {
            "kind": evidence.kind,
            "service_namespace": evidence.service_namespace,
            "service_name": evidence.service_name,
            "limit": limit,
        }
        if isinstance(evidence, SemanticExecutionReference):
            params["executable_type"] = evidence.executable_type.value
            params["runtime_id"] = evidence.runtime_id
        else:
            params["trace_id"] = evidence.trace_id
            params["span_id"] = evidence.span_id
        if cursor is not None:
            params["cursor"] = cursor
        return await self._model_request(
            "GET",
            f"{self._EVALUATION_PREFIX}/evidence-membership",
            EvidenceMembershipList,
            params=params,
        )

    async def _model_request(
        self,
        method: str,
        path: str,
        model: type[ResponseT],
        *,
        json: object | None = None,
        params: dict[str, str | int] | None = None,
    ) -> ResponseT:
        response = await self._request(
            method,
            path,
            json=json,
            params=params,
            max_response_bytes=self._max_control_response_bytes,
        )
        self._raise_for_status(response, method=method, path=path)
        return self._parse(response, model)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        params: dict[str, str | int] | None = None,
        max_response_bytes: int,
    ) -> _BufferedResponse:
        for attempt_index in range(self._retry_attempts):
            try:
                async with self._http.stream(
                    method,
                    path,
                    json=json,
                    params=params,
                ) as response:
                    content = await _read_bounded(
                        response,
                        path=path,
                        max_bytes=max_response_bytes,
                    )
                    buffered = _BufferedResponse(
                        status_code=response.status_code,
                        content=content,
                    )
            except httpx.TransportError as error:
                if attempt_index + 1 >= self._retry_attempts:
                    raise StudioTransientError(
                        method=method,
                        path=path,
                        status_code=None,
                    ) from error
                await self._backoff(attempt_index)
                continue

            if buffered.status_code not in _RETRYABLE_STATUS_CODES:
                return buffered
            if attempt_index + 1 >= self._retry_attempts:
                raise StudioTransientError(
                    method=method,
                    path=path,
                    status_code=buffered.status_code,
                )
            await self._backoff(attempt_index)

        raise AssertionError("retry loop exhausted without returning or raising")

    async def _backoff(self, attempt_index: int) -> None:
        delay = min(self._retry_backoff_seconds * (2**attempt_index), 2.0)
        if delay > 0:
            await asyncio.sleep(delay)

    @staticmethod
    def _parse(
        response: _BufferedResponse,
        model: type[ResponseT],
    ) -> ResponseT:
        try:
            return model.model_validate_json(response.content)
        except (ValueError, ValidationError) as error:
            raise StudioContractError(f"Studio response did not match {model.__name__}.") from error

    @classmethod
    def _raise_for_status(
        cls,
        response: _BufferedResponse,
        *,
        method: str,
        path: str,
    ) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code == 401:
            raise StudioAuthenticationError("Studio authentication is not authorized.")
        if response.status_code == 403:
            raise StudioAuthorizationError("Studio authority lacks a required scope.")
        if response.status_code == 409:
            conflict = cls._parse(response, ConflictResponse)
            raise StudioConflictError(
                method=method,
                path=path,
                code=conflict.code,
                detail=conflict.message,
            )
        if response.status_code == 422:
            raise StudioValidationError(method=method, path=path)
        raise StudioRequestError(
            method=method,
            path=path,
            status_code=response.status_code,
        )


async def _read_bounded(
    response: httpx.Response,
    *,
    path: str,
    max_bytes: int,
) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > max_bytes:
            raise StudioResponseTooLargeError(path=path, max_bytes=max_bytes)

    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise StudioResponseTooLargeError(path=path, max_bytes=max_bytes)
        content.extend(chunk)
    return bytes(content)


def _validate_base_url(base_url: str) -> str:
    try:
        url = httpx.URL(base_url)
    except (TypeError, ValueError) as error:
        raise ValueError("base_url must be a valid Studio origin.") from error
    if url.scheme not in {"http", "https"} or url.host is None:
        raise ValueError("base_url must be an absolute HTTP or HTTPS Studio origin.")
    if url.username or url.password:
        raise ValueError("base_url must not contain credentials.")
    if url.query or url.fragment:
        raise ValueError("base_url must not contain a query or fragment.")
    if url.path not in {"", "/"}:
        raise ValueError("base_url must be an origin without an application path.")
    if url.scheme == "http" and not _is_loopback_host(url.host):
        raise ValueError("Plain HTTP Studio origins are allowed only on loopback.")
    return str(url)


def _is_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_token(token: str | SecretStr | None) -> SecretStr | None:
    if token is None:
        return None
    secret = token if isinstance(token, SecretStr) else SecretStr(token)
    value = secret.get_secret_value()
    if not value or value != value.strip():
        raise ValueError("Studio token must be non-empty and contain no surrounding whitespace.")
    return secret


def _require_positive_float(field_name: str, value: float) -> None:
    if value <= 0 or value > 300:
        raise ValueError(f"{field_name} must be greater than 0 and at most 300.")


def _require_response_bound(field_name: str, value: int) -> None:
    if not 1 <= value <= 256 * 1024 * 1024:
        raise ValueError(f"{field_name} must be between 1 byte and 256 MiB.")


def _require_page_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"Studio evaluation page limit must be between 1 and {MAX_PAGE_SIZE}.")


def _validated_record_id(value: str) -> str:
    return _RECORD_ID.validate_python(value, strict=True)


def _validated_cursor(value: str | None) -> str | None:
    if value is None:
        return None
    return _CURSOR_TEXT.validate_python(value, strict=True)


def _validate_trace_id(value: str) -> str:
    value = _TRACE_ID.validate_python(value, strict=True)
    if len(value) != 32 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("trace_id must contain exactly 32 lowercase hexadecimal characters.")
    return value


def _path_segment(value: str) -> str:
    return quote(value, safe="")
