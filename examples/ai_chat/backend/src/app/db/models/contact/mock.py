from datetime import datetime

from app.db.models.contact.schemas import ContactRead, GenderEnum


def create_mock_contact_read() -> ContactRead:
    """Creates a mock ContactRead instance for testing."""
    return ContactRead(
        id="mock_contact_id",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        gender=GenderEnum.MALE,
        first_name="John",
        last_name="Doe",
        age=30,
        weight_lbs=180.5,
        us_state="CA",
        city="Los Angeles",
        bio="A mock contact for testing purposes.",
    )
