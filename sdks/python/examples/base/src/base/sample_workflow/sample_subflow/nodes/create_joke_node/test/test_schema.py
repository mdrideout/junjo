from pydantic import BaseModel


class TestCreateJokeSchema(BaseModel):
    """Schema for the response of the evaluation of the create_joke node."""
    passed: bool
    reason: str
