from pydantic import BaseModel, ConfigDict


class BaseState(BaseModel):
    """Common base for states, with no unknown fields allowed."""
    model_config = ConfigDict(extra='forbid')
