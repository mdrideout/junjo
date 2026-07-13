from pydantic import BaseModel


class LocCityState(BaseModel):
    city: str
    state: str
