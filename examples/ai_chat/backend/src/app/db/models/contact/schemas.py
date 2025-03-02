from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GenderEnum(Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ContactCreate(BaseModel):
    gender: GenderEnum
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    age: int = Field(..., ge=18, lt=130)
    weight_lbs: float = Field(..., ge=75, lt=500)
    us_state: str = Field(..., max_length=50)
    city: str = Field(..., max_length=100)
    bio: str = Field(..., max_length=1000)

    model_config = ConfigDict(from_attributes=True)


class ContactCreateGeminiSchema(BaseModel):
    """A clone of the Create model for Gemini, which does not support the Field extras."""

    gender: GenderEnum
    first_name: str
    last_name: str
    age: int
    weight_lbs: float
    us_state: str
    city: str
    bio: str


class ContactRead(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    gender: GenderEnum
    first_name: str
    last_name: str
    age: int
    weight_lbs: float
    us_state: str
    city: str
    bio: str

    model_config = ConfigDict(from_attributes=True)


class ContactDelete(BaseModel):
    id: str
