"""Register every SQLAlchemy model with the shared metadata.

Alembic, application startup, and tests import this module before reading
``Base.metadata``. New tables belong in this explicit registry.
"""

from app.db_sqlite.api_keys.models import APIKeyTable  # noqa: F401
from app.db_sqlite.evaluation.models import (  # noqa: F401
    EvaluationCaseAttemptTable,
    EvaluationCaseTable,
    EvaluationDatasetTable,
    EvaluationRunTable,
)
from app.db_sqlite.evaluation_tokens.models import EvaluationTokenTable  # noqa: F401
from app.db_sqlite.users.models import UserTable  # noqa: F401
