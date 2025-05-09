
from junjo.state import BaseState
from junjo.store import BaseStore

from app.db.models.contact.schemas import ContactRead, Sex
from app.workflows.create_contact.nodes.select_location.schemas import LocCityState
from app.workflows.create_contact.schemas import PersonalityTraits


class CreateContactState(BaseState):
    sex: Sex | None = None
    loc_lat: float | None = None
    loc_lon: float | None = None
    location: LocCityState | None = None
    personality_traits: PersonalityTraits | None = None
    bio: str | None = None
    avatar_id: str | None = None
    final_contact: ContactRead | None = None

class CreateContactStore(BaseStore[CreateContactState]):
    """
    A concrete store for CreateContactState.
    """

    async def set_sex(self, payload: Sex) -> None:
        await self.set_state({"sex": payload})

    async def set_loc_lat(self, payload: float) -> None:
        await self.set_state({"loc_lat": payload})

    async def set_loc_lon(self, payload: float) -> None:
        await self.set_state({"loc_lon": payload})

    async def set_location(self, payload: LocCityState) -> None:
        await self.set_state({"location": payload})

    async def set_personality_traits(self, payload: PersonalityTraits) -> None:
        await self.set_state({"personality_traits": payload})

    async def set_bio(self, payload: str) -> None:
        await self.set_state({"bio": payload})

    async def set_avatar_id(self, payload: str) -> None:
        await self.set_state({"avatar_id": payload})

    async def set_final_contact(self, payload: ContactRead) -> None:
        await self.set_state({"final_contact": payload})
