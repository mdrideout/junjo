from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Sex(StrEnum):
    """Sex of the contact"""
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"



class ContactCreate(BaseModel):
    avatar_id: str
    sex: Sex
    first_name: str
    last_name: str
    age: int
    openness: float
    conscientiousness: float
    neuroticism: float
    agreeableness: float
    extraversion: float
    intelligence: float
    religiousness: float
    attractiveness: float
    trauma: float
    latitude: float
    longitude: float
    city: str
    state: str
    bio: str


class ContactRead(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    avatar_id: str
    sex: Sex
    first_name: str
    last_name: str
    age: int
    openness: float
    conscientiousness: float
    neuroticism: float
    agreeableness: float
    extraversion: float
    intelligence: float
    religiousness: float
    attractiveness: float
    trauma: float
    latitude: float
    longitude: float
    city: str
    state: str
    bio: str

    model_config = ConfigDict(from_attributes=True)




class ContactDelete(BaseModel):
    id: str
