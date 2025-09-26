from __future__ import annotations

import json
from collections.abc import Hashable
from functools import lru_cache
from typing import TYPE_CHECKING, Optional, Sequence, TypeVar

from pydantic import BaseModel, Field
from thefuzz import process


if TYPE_CHECKING:
    from .cache_handler import CacheHandler

T = TypeVar("T", bound=Hashable)


class Symptom(BaseModel, Hashable):
    name: str
    what_is_it: str
    trimesters: list[str]
    description: str
    remedies: list[str]
    when_to_call_doctor: str
    sources: str
    # sources is markdown text

    def __hash__(self) -> int:
        return hash(self.name)


class TrimesterData(BaseModel, Hashable):
    week_number: int = Field(alias="weekNumber")
    baby_tip_text: str = Field(alias="babyTipText")
    mom_tip_text: str = Field(alias="momTipText")
    quote: Optional[str] = None
    image_uri: Optional[str] = Field(None, alias="imageUri")
    baby_image_uri: Optional[str] = Field(None, alias="babyImageUri")
    baby_height_in_centimeters: Optional[float] = Field(None, alias="babyHeightInCentimeters")
    baby_weight_in_grams: Optional[float] = Field(None, alias="babyWeightInGrams")


with open("static/symptoms_data.json", "r") as f:
    SYMPTOMS_DATA = json.load(f)

with open("static/trimester_data.json", "r") as f:
    TRIMESTER_DATA = json.load(f)

SYMPTOMS = tuple(Symptom(**item) for item in SYMPTOMS_DATA)
TRIMESTERS = tuple(TrimesterData(**item) for item in TRIMESTER_DATA)


class Finder:  # Imagine using MacOS
    def __init__(self, cache_handler: CacheHandler | None = None) -> None:
        self.cache_handler = cache_handler

    @lru_cache(maxsize=128)
    def fuzzy_search(self, query, choices: Sequence[T], **kwargs) -> list[T]:
        results = process.extract(query, choices, **kwargs)
        return [result[0] for result in results]

    def search_symptoms(self, query: str = "", limit: int | None = None) -> list[Symptom]:
        return self.fuzzy_search(query, SYMPTOMS, limit=limit)

    def search_trimester(self, week_number: int) -> Optional[TrimesterData]:
        for trimester in TRIMESTERS:
            if trimester.week_number == week_number:
                return trimester
        return None
