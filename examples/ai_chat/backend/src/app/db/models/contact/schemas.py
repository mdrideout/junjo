from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Sex(StrEnum):
    """Sex of the contact"""
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"



class ContactCreate(BaseModel):
    sex: Sex
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
    sex: Sex
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
