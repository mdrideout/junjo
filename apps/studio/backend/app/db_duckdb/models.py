"""DuckDB data models for OTEL spans.

Note: These models are primarily for documentation and type hints.
Actual inserts use raw SQL for performance (batch inserts with duckdb.executemany()).

DuckDB excels at bulk inserts with raw SQL, and using SQLAlchemy ORM would
add unnecessary overhead for write operations. We use raw SQL for inserts
and can use SQLAlchemy for reads if needed in the future.
"""

from pydantic import BaseModel, ConfigDict


class Span(BaseModel):
    """OpenTelemetry span with Junjo custom fields.

    Represents a single span stored in DuckDB.
    """

    # Primary Key
    trace_id: str  # 32-char hex
    span_id: str  # 16-char hex

    # OTEL Standard Fields
    parent_span_id: str | None = None
    service_name: str
    name: str | None = None
    kind: str | None = None  # "CLIENT", "SERVER", "INTERNAL", etc.
    start_time: str  # ISO 8601 timestamp
    end_time: str  # ISO 8601 timestamp
    status_code: str | None = None
    status_message: str | None = None
    attributes_json: dict | None = None
    events_json: list | None = None
    links_json: list | None = None
    trace_flags: int | None = None
    trace_state: str | None = None

    # Junjo Custom Fields
    junjo_id: str | None = None
    junjo_parent_id: str | None = None
    junjo_span_type: str | None = None  # "workflow", "subflow", "node"

    # Workflow State (workflow/subflow spans only)
    junjo_wf_state_start: dict | None = None
    junjo_wf_state_end: dict | None = None
    junjo_wf_graph_structure: dict | None = None
    junjo_wf_store_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StatePatch(BaseModel):
    """State patch from workflow execution.

    Represents incremental state changes from "set_state" events.
    """

    patch_id: str  # UUID
    service_name: str
    trace_id: str  # FK to spans
    span_id: str  # FK to spans
    workflow_id: str
    node_id: str
    event_time: str  # ISO 8601 timestamp
    patch_json: dict  # JSON patch data
    patch_store_id: str

    model_config = ConfigDict(from_attributes=True)
