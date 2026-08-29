"""Bounded, application-owned place facts for the local-place evaluation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecommendedPlaceClaim(BaseModel):
    """One venue and only the location details stated in the response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    street_or_address: str | None = None
    neighborhood: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Recommended place name cannot be blank.")
        return normalized

    @field_validator("street_or_address", "neighborhood")
    @classmethod
    def normalize_optional_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class VerifiedPlace:
    """One place fact checked against the named source on ``verified_on``."""

    id: str
    name: str
    aliases: tuple[str, ...]
    neighborhood: str
    address: str
    operating: bool
    source_name: str
    source_url: str
    verified_on: str


@dataclass(frozen=True, slots=True)
class PlaceVerification:
    """One deterministic decision against the bounded place snapshot."""

    passed: bool
    reason: str


_VERIFIED_ON = "2026-08-29"

VERIFIED_PLACES = (
    VerifiedPlace(
        id="gold-star-beer-counter",
        name="Gold Star Beer Counter",
        aliases=("Gold Star Beer Counter",),
        neighborhood="Prospect Heights",
        address="176 Underhill Avenue, Brooklyn, NY 11238",
        operating=True,
        source_name="Gold Star Beer Counter official site",
        source_url="https://goldstarbeercounter.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="bierwax",
        name="BierWax",
        aliases=("BierWax",),
        neighborhood="Prospect Heights",
        address="556 Vanderbilt Avenue, Brooklyn, NY 11238",
        operating=True,
        source_name="BierWax official site",
        source_url="https://www.bierwaxnyc.com/location",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="dynaco",
        name="Dynaco",
        aliases=("Dynaco",),
        neighborhood="Bedford-Stuyvesant",
        address="1112 Bedford Avenue, Brooklyn, NY 11216",
        operating=True,
        source_name="Eater NY venue record",
        source_url="https://ny.eater.com/venue/39057/dynaco",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="lunatico",
        name="LunÀtico",
        aliases=("LunÀtico", "Bar LunÀtico", "Lunatico", "Bar Lunatico"),
        neighborhood="Bedford-Stuyvesant",
        address="486 Halsey Street, Brooklyn, NY 11233",
        operating=True,
        source_name="LunÀtico official site",
        source_url="https://www.barlunatico.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="saraghina-bakery",
        name="Saraghina Bakery",
        aliases=("Saraghina Bakery",),
        neighborhood="Bedford-Stuyvesant",
        address="433 Halsey Street, Brooklyn, NY 11233",
        operating=True,
        source_name="Saraghina official site",
        source_url="https://www.saraghina.com/saraghina-bakery",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="saraghina-caffe",
        name="Saraghina Caffè",
        aliases=("Saraghina Caffe", "Saraghina Café", "Saraghina Caffè"),
        neighborhood="Fort Greene",
        address="195 DeKalb Avenue, Brooklyn, NY 11205",
        operating=True,
        source_name="Saraghina official site",
        source_url="https://www.saraghina.com/about-us",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="corto",
        name="Corto",
        aliases=("Corto",),
        neighborhood="Bedford-Stuyvesant",
        address="262 Halsey Street, Brooklyn, NY 11216",
        operating=True,
        source_name="Corto official site",
        source_url="https://www.cortonyc.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="sincerely-tommy",
        name="Sincerely, Tommy",
        aliases=("Sincerely, Tommy", "Sincerely Tommy"),
        neighborhood="Bedford-Stuyvesant",
        address="343 Tompkins Avenue, Brooklyn, NY 11216",
        operating=True,
        source_name="Sincerely, Tommy official site",
        source_url="https://sincerelytommy.com/pages/contact",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="herbert-von-king-park",
        name="Herbert Von King Park",
        aliases=("Herbert Von King Park",),
        neighborhood="Bedford-Stuyvesant",
        address=(
            "Marcy Avenue and Tompkins Avenue between Greene Avenue and "
            "Lafayette Avenue, Brooklyn, NY 11216"
        ),
        operating=True,
        source_name="NYC Open Data accessible parks directory",
        source_url=(
            "https://data.cityofnewyork.us/Recreation/"
            "Directory-of-Accessible-Parks-Facilities-and-Prog/e4ej-j6hn/about_data"
        ),
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="ras-plant-based",
        name="RAS Plant Based",
        aliases=("RAS Plant Based", "Ras Plant Based"),
        neighborhood="Crown Heights",
        address="739 Franklin Avenue, Brooklyn, NY 11238",
        operating=True,
        source_name="RAS Plant Based official site",
        source_url="https://www.rasplantbased.com/location/ras-planted-based-brooklyn/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="king-tai",
        name="King Tai",
        aliases=("King Tai", "King Tai Bar"),
        neighborhood="Crown Heights",
        address="1095 Bergen Street, Brooklyn, NY 11216",
        operating=True,
        source_name="King Tai official site",
        source_url="https://www.kingtaibar.com/about",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="la-napa",
        name="La Ñapa",
        aliases=("La Ñapa", "La Napa"),
        neighborhood="Crown Heights",
        address="656 Nostrand Avenue, Brooklyn, NY 11216",
        operating=True,
        source_name="La Ñapa official site",
        source_url="https://lanapamarket.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="peppas-jerk-chicken",
        name="Peppa's Jerk Chicken",
        aliases=("Peppa's Jerk Chicken", "Peppas Jerk Chicken", "Peppa's"),
        neighborhood="Crown Heights",
        address="791 Prospect Place, Brooklyn, NY 11216",
        operating=True,
        source_name="Peppa's Jerk Chicken official site",
        source_url="https://peppasonline.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="savvy-bistro",
        name="Savvy Bistro & Bar",
        aliases=("Savvy Bistro & Bar", "Savvy Bistro"),
        neighborhood="Crown Heights",
        address="710 Nostrand Avenue, Brooklyn, NY 11216",
        operating=True,
        source_name="Savvy Bistro & Bar official site",
        source_url="https://savvybistro.com/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="the-islands",
        name="The Islands",
        aliases=(
            "The Islands",
            "The Islands on Franklin",
            "The Islands on Washington",
            "The Islands restaurant",
        ),
        neighborhood="Prospect Heights",
        address="671 Washington Avenue, Brooklyn, NY 11238",
        operating=False,
        source_name="Apple Maps place record",
        source_url="https://maps.apple.com/place?place-id=IF58A648E00BC0745",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="books-are-magic-smith",
        name="Books Are Magic (Smith Street)",
        aliases=("Books Are Magic",),
        neighborhood="Cobble Hill",
        address="225 Smith Street, Brooklyn, NY 11231",
        operating=True,
        source_name="New York State Literary Tree record",
        source_url="https://nyslittree.org/locations/books-are-magic/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="center-for-fiction",
        name="The Center for Fiction",
        aliases=("The Center for Fiction", "Center for Fiction"),
        neighborhood="Downtown Brooklyn",
        address="15 Lafayette Avenue, Brooklyn, NY 11217",
        operating=True,
        source_name="The Center for Fiction official site",
        source_url="https://centerforfiction.org/visit/",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="bien-cuit-smith",
        name="Bien Cuit (Smith Street)",
        aliases=("Bien Cuit",),
        neighborhood="Boerum Hill",
        address="120 Smith Street, Brooklyn, NY 11201",
        operating=True,
        source_name="Bien Cuit official site",
        source_url="https://www.biencuit.com/locations",
        verified_on=_VERIFIED_ON,
    ),
    VerifiedPlace(
        id="swallow-cafe-cobble-hill",
        name="Swallow Cafe (Cobble Hill)",
        aliases=("Swallow Cafe",),
        neighborhood="Cobble Hill",
        address="156 Atlantic Avenue, Brooklyn, NY 11201",
        operating=True,
        source_name="Nooklyn current place record",
        source_url="https://nooklyn.com/locations/lJK7XB3Je5yYt0IwIm9d",
        verified_on=_VERIFIED_ON,
    ),
)

VERIFIED_PLACES_BY_ID = {place.id: place for place in VERIFIED_PLACES}


def verify_local_place_claims(
    claims: tuple[RecommendedPlaceClaim, ...],
    *,
    verified_place_ids: tuple[str, ...],
    minimum_verified_places: int,
) -> PlaceVerification:
    """Check every extracted recommendation against one Case's place snapshot."""

    unknown_ids = set(verified_place_ids).difference(VERIFIED_PLACES_BY_ID)
    if unknown_ids:
        unknown = ", ".join(sorted(unknown_ids))
        raise ValueError(f"Unknown verified place IDs: {unknown}.")

    matched: list[VerifiedPlace] = []
    for claim in claims:
        place = _place_for_claim(claim)
        if place is None:
            return PlaceVerification(
                passed=False,
                reason=(
                    "Current-place check failed: "
                    f"{claim.name!r} is not in this evaluator's source-verified snapshot "
                    f"(verified {_VERIFIED_ON})."
                ),
            )
        if not place.operating:
            return PlaceVerification(
                passed=False,
                reason=(
                    f"Current-place check failed: {place.name} is permanently closed and is "
                    f"recorded at {place.address}, not as a current recommendation "
                    f"({place.source_name}, verified {place.verified_on}: {place.source_url})."
                ),
            )
        if place.id not in verified_place_ids:
            return PlaceVerification(
                passed=False,
                reason=(
                    f"Current-place check failed: {place.name} is recorded in "
                    f"{place.neighborhood} at {place.address}, outside this case's verified place set "
                    f"({place.source_name}, verified {place.verified_on}: {place.source_url})."
                ),
            )
        location_error = _location_error(claim, place)
        if location_error is not None:
            return PlaceVerification(passed=False, reason=location_error)
        if place not in matched:
            matched.append(place)

    if len(matched) < minimum_verified_places:
        observed = ", ".join(place.name for place in matched) or "none"
        return PlaceVerification(
            passed=False,
            reason=(
                "Current-place check failed: "
                f"found {len(matched)} of {minimum_verified_places} required current place(s) "
                f"from this case's verified snapshot; recognized: {observed}. "
                f"Snapshot verified {_VERIFIED_ON}."
            ),
        )

    evidence = "; ".join(
        f"{place.name} at {place.address} ({place.source_name})" for place in matched
    )
    return PlaceVerification(
        passed=True,
        reason=f"Current-place check passed: {evidence}; verified {_VERIFIED_ON}.",
    )


def _place_for_claim(claim: RecommendedPlaceClaim) -> VerifiedPlace | None:
    normalized_name = _normalize(claim.name)
    return next(
        (
            place
            for place in VERIFIED_PLACES
            if normalized_name in {_normalize(alias) for alias in place.aliases}
        ),
        None,
    )


def _location_error(claim: RecommendedPlaceClaim, place: VerifiedPlace) -> str | None:
    if claim.street_or_address is not None:
        claimed_address = _normalize_location(claim.street_or_address)
        recorded_address = _normalize_location(place.address)
        claimed_numbers = re.findall(r"(?<!\w)\d+[a-z]?(?!\w)", claimed_address)
        recorded_numbers = re.findall(r"(?<!\w)\d+[a-z]?(?!\w)", recorded_address)
        number_mismatch = bool(claimed_numbers) and (
            not recorded_numbers or claimed_numbers[0] != recorded_numbers[0]
        )
        address_mismatch = (
            claimed_address not in recorded_address
            and recorded_address not in claimed_address
        )
        if number_mismatch or address_mismatch:
            return (
                f"Current-place check failed: {claim.name} was described at "
                f"{claim.street_or_address}, but {place.source_name} records {place.address} "
                f"(verified {place.verified_on}: {place.source_url})."
            )
    if claim.neighborhood is not None:
        claimed_neighborhood = _normalize_neighborhood(claim.neighborhood)
        accepted_neighborhoods = {
            _normalize_neighborhood(name)
            for name in _accepted_neighborhood_claims(place)
        }
        if claimed_neighborhood not in accepted_neighborhoods:
            return (
                f"Current-place check failed: {claim.name} was described in "
                f"{claim.neighborhood}, but {place.source_name} records "
                f"{place.neighborhood} at {place.address} "
                f"(verified {place.verified_on}: {place.source_url})."
            )
    return None


def _normalize(value: str) -> str:
    punctuation_normalized = value.translate(
        str.maketrans(
            {
                "’": "'",
                "‘": "'",
                "–": "-",
                "—": "-",
            }
        )
    )
    decomposed = unicodedata.normalize("NFKD", punctuation_normalized.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def _normalize_location(value: str) -> str:
    normalized = _normalize(value).replace(",", "").replace(".", "")
    substitutions = {
        " avenue": " ave",
        " street": " st",
        " road": " rd",
        " boulevard": " blvd",
    }
    for full, abbreviation in substitutions.items():
        normalized = normalized.replace(full, abbreviation)
    return normalized


def _normalize_neighborhood(value: str) -> str:
    normalized = _normalize(value).replace(",", "")
    if normalized.endswith(" brooklyn"):
        normalized = normalized.removesuffix(" brooklyn")
    aliases = {
        "bed stuy": "bedford-stuyvesant",
        "bed-stuy": "bedford-stuyvesant",
        "bedford stuyvesant": "bedford-stuyvesant",
    }
    return aliases.get(normalized, normalized)


def _accepted_neighborhood_claims(place: VerifiedPlace) -> tuple[str, ...]:
    if place.id == "books-are-magic-smith":
        return (
            place.neighborhood,
            "Boerum Hill",
            "Cobble Hill and Boerum Hill border",
        )
    if place.id == "center-for-fiction":
        return (
            place.neighborhood,
            "Fort Greene",
            "Brooklyn Cultural District",
        )
    return (place.neighborhood,)
