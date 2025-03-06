
from contextvars import ContextVar

from junjo.workflow_context import WorkflowContextManager


class JunjoApp:
    """A class to hold the configuration of a Junjo project."""

    # Context variables
    _project_name: ContextVar[str] = ContextVar("project_name")

    def __init__(self, project_name: str):
        """Initialize the JunjoConfig by setting context variables."""
        # Setup the workflow context manager
        WorkflowContextManager()

        # Set the context variables
        self._project_name.set(project_name)


    async def init(self):
        """Perform initialization tasks required at startup."""
        pass

    @property
    def project_name(self) -> str:
        """Get the project name."""
        return self._project_name.get()


