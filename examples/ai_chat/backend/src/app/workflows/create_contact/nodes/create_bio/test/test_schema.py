from pydantic import BaseModel


class TestCreateBioSchema(BaseModel):
    """Schema for the response of the evaluation of the create_bio node."""
    passed: bool
    reason: str
