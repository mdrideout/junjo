from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GenderEnum(Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ContactCreate(BaseModel):
    gender: GenderEnum
    first_name:str = Field(..., max_length=255)
    last_name:str = Field(..., max_length=255)
    age:int = Field(..., ge=0)
    weight_lbs:float = Field(..., ge=0)
    us_state:str = Field(..., max_length=255)
    city:str = Field(..., max_length=255)
    bio:str = Field(..., max_length=1024)


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

