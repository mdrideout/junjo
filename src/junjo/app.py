
from contextvars import ContextVar

from junjo.database.tortoise import JunjoDatabase


class JunjoApp:
    """A class to hold the configuration of a Junjo project."""

    # Context variables
    _project_name: ContextVar[str] = ContextVar("project_name")
    _sqlite_url: ContextVar[str | None] = ContextVar("sqlite_url")

    def __init__(self, project_name: str, sqlite_url: str | None = None):
        """Initialize the JunjoConfig by setting context variables."""
        self._project_name.set(project_name)
        self._sqlite_url.set(sqlite_url)

    async def init(self):
        """Perform initialization tasks required at startup."""
        if self.sqlite_url:
            # Initialize the database
            await JunjoDatabase.init_db(self.sqlite_url)

    @property
    def project_name(self) -> str:
        """Get the project name."""
        return self._project_name.get()

    @property
    def sqlite_url(self) -> str | None:
        """Get the SQLite URL."""
        return self._sqlite_url.get()


