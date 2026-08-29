"""Calibration tests for AI Chat's bounded current-place verifier."""

from types import SimpleNamespace
from typing import TypeVar, cast

import pytest
from junjo.evaluation import EvaluationContext
from pydantic import BaseModel

from ai_chat.evals.harness import (
    EvaluationRuntime,
    LocalPlaceQualityExpectationV1,
    _local_place_quality_callback,
)
from ai_chat.evals.local_places import RecommendedPlaceClaim, verify_local_place_claims

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class _QualityLanguage:
    def __init__(self, *, passed: bool, places: tuple[dict[str, str | None], ...]) -> None:
        self.passed = passed
        self.places = places
        self.calls = 0

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        self.calls += 1
        assert "ASSISTANT RESPONSE" in prompt
        return output_type.model_validate(
            {
                "passed": self.passed,
                "reason": "The response fits the requested date." if self.passed else "The response is not low-key.",
                "places": self.places,
            }
        )


def test_known_current_place_passes_with_source_evidence() -> None:
    result = verify_local_place_claims(
        (_claim("BierWax", street="Vanderbilt Avenue"),),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )

    assert result.passed is True
    assert "556 Vanderbilt Avenue" in result.reason
    assert "BierWax official site" in result.reason
    assert "verified 2026-08-29" in result.reason


def test_known_closed_and_mislocated_place_fails_before_quality_judgment() -> None:
    result = verify_local_place_claims(
        (_claim("The Islands", street="Franklin Ave"),),
        verified_place_ids=("la-napa", "peppas-jerk-chicken", "savvy-bistro"),
        minimum_verified_places=1,
    )

    assert result.passed is False
    assert "permanently closed" in result.reason
    assert "671 Washington Avenue" in result.reason
    assert "Apple Maps place record" in result.reason


def test_accented_place_alias_is_matched_without_fuzzy_guessing() -> None:
    result = verify_local_place_claims(
        (_claim("Bar Lunatico", street="Halsey Street"),),
        verified_place_ids=("lunatico",),
        minimum_verified_places=1,
    )

    assert result.passed is True
    assert "LunÀtico" in result.reason

    boundary = verify_local_place_claims(
        (_claim("BierWaxed"),),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )
    assert boundary.passed is False
    assert "not in this evaluator's source-verified snapshot" in boundary.reason


def test_two_place_case_requires_two_verified_matches() -> None:
    one_place = verify_local_place_claims(
        (_claim("Corto"),),
        verified_place_ids=("corto", "sincerely-tommy"),
        minimum_verified_places=2,
    )
    two_places = verify_local_place_claims(
        (_claim("Corto"), _claim("Sincerely, Tommy")),
        verified_place_ids=("corto", "sincerely-tommy"),
        minimum_verified_places=2,
    )

    assert one_place.passed is False
    assert "found 1 of 2" in one_place.reason
    assert two_places.passed is True


def test_current_place_outside_the_case_geography_fails() -> None:
    result = verify_local_place_claims(
        (_claim("Bar LunÀtico"), _claim("Saraghina Caffe")),
        verified_place_ids=("lunatico", "saraghina-bakery"),
        minimum_verified_places=1,
    )

    assert result.passed is False
    assert "Saraghina Caffè" in result.reason
    assert "Fort Greene" in result.reason


def test_unknown_place_identity_is_a_contract_error() -> None:
    with pytest.raises(ValueError, match="Unknown verified place IDs: imaginary-place"):
        verify_local_place_claims(
            (_claim("Somewhere"),),
            verified_place_ids=("imaginary-place",),
            minimum_verified_places=1,
        )


async def test_composite_evaluator_short_circuits_known_bad_fact() -> None:
    expectation = LocalPlaceQualityExpectationV1(
        rubric="Recommend a current Crown Heights Caribbean restaurant.",
        verified_place_ids=("la-napa", "peppas-jerk-chicken", "savvy-bistro"),
    )

    language = _QualityLanguage(
        passed=True,
        places=({"name": "The Islands", "street_or_address": "Franklin Ave", "neighborhood": None},),
    )
    resources = SimpleNamespace(provider=SimpleNamespace(language=language))

    result = await _local_place_quality_callback(
        "PROFILE:\n{}\n\nCURRENT USER MESSAGE:\nDinner?\n\n"
        "ASSISTANT RESPONSE:\nTry The Islands on Franklin Ave.",
        expectation,
        cast(EvaluationContext, object()),
        cast(EvaluationRuntime, resources),
    )

    assert result.passed is False
    assert "permanently closed" in result.reason
    assert language.calls == 1


@pytest.mark.parametrize("quality_passed", [True, False])
async def test_composite_evaluator_requires_both_checks(quality_passed: bool) -> None:
    language = _QualityLanguage(
        passed=quality_passed,
        places=({"name": "BierWax", "street_or_address": None, "neighborhood": None},),
    )
    resources = SimpleNamespace(provider=SimpleNamespace(language=language))
    expectation = LocalPlaceQualityExpectationV1(
        rubric="Recommend a current low-key Prospect Heights date place.",
        verified_place_ids=("bierwax",),
    )

    result = await _local_place_quality_callback(
        "PROFILE:\n{}\n\nCURRENT USER MESSAGE:\nDinner?\n\n"
        "ASSISTANT RESPONSE:\nTry BierWax for a relaxed drink.",
        expectation,
        cast(EvaluationContext, object()),
        cast(EvaluationRuntime, resources),
    )

    assert result.passed is quality_passed
    assert language.calls == 1
    assert "Current-place check passed" in result.reason
    assert f"Qualitative check {'passed' if quality_passed else 'failed'}" in result.reason


def test_allowed_place_does_not_hide_unknown_extra_or_false_location() -> None:
    unknown_extra = verify_local_place_claims(
        (_claim("BierWax"), _claim("Imaginary Unicorn Cafe")),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )
    false_location = verify_local_place_claims(
        (_claim("BierWax", street="999 Fake Street", neighborhood="Queens"),),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )

    assert unknown_extra.passed is False
    assert "Imaginary Unicorn Cafe" in unknown_extra.reason
    assert false_location.passed is False
    assert "999 Fake Street" in false_location.reason
    assert "556 Vanderbilt Avenue" in false_location.reason


def test_address_number_is_exact_while_normal_punctuation_is_ignored() -> None:
    wrong_number = verify_local_place_claims(
        (_claim("BierWax", street="56 Vanderbilt Ave"),),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )
    punctuated = verify_local_place_claims(
        (_claim("BierWax", street="556 Vanderbilt Ave."),),
        verified_place_ids=("bierwax",),
        minimum_verified_places=1,
    )

    assert wrong_number.passed is False
    assert "56 Vanderbilt Ave" in wrong_number.reason
    assert punctuated.passed is True


def test_curly_apostrophe_matches_canonical_place_name() -> None:
    result = verify_local_place_claims(
        (_claim("Peppa’s Jerk Chicken"),),
        verified_place_ids=("peppas-jerk-chicken",),
        minimum_verified_places=1,
    )

    assert result.passed is True


def test_neighborhood_claims_accept_local_name_variants() -> None:
    bed_stuy = verify_local_place_claims(
        (_claim("LunÀtico", neighborhood="Bed-Stuy, Brooklyn"),),
        verified_place_ids=("lunatico",),
        minimum_verified_places=1,
    )
    border = verify_local_place_claims(
        (_claim("Books Are Magic", neighborhood="Boerum Hill"),),
        verified_place_ids=("books-are-magic-smith",),
        minimum_verified_places=1,
    )

    assert bed_stuy.passed is True
    assert border.passed is True


def _claim(
    name: str,
    *,
    street: str | None = None,
    neighborhood: str | None = None,
) -> RecommendedPlaceClaim:
    return RecommendedPlaceClaim(
        name=name,
        street_or_address=street,
        neighborhood=neighborhood,
    )
