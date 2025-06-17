from pydantic import BaseModel


class Task(BaseModel):
    """A task definition."""
    id: str
    name: str
    duration_minutes: float | None = None

