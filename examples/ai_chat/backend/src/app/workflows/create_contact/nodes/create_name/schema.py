from pydantic import BaseModel


class CreateNameSchema(BaseModel):
    """Schema for AI-generated name."""
    first_name: str
    last_name: str
