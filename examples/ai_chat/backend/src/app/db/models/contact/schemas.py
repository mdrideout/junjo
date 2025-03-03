from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class GenderEnum(Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class ContactCreate(BaseModel):
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
