from __future__ import annotations

import json
from collections.abc import Hashable
from functools import lru_cache
from typing import TYPE_CHECKING, Sequence, TypeVar

from pydantic import BaseModel
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


with open("static/symptoms_data.json", "r") as f:
    SYMPTOMS_DATA = json.load(f)

SYMPTOMS = tuple(Symptom(**item) for item in SYMPTOMS_DATA)


class Finder:  # Imagine using MacOS
    def __init__(self, cache_handler: CacheHandler | None = None) -> None:
        self.cache_handler = cache_handler

    @lru_cache(maxsize=128)
    def fuzzy_search(self, query, choices: Sequence[T], **kwargs) -> list[T]:
        results = process.extract(query, choices, **kwargs)
        return [result[0] for result in results]

    def search_symptoms(self, query: str = "", limit: int | None = None) -> list[Symptom]:
        return self.fuzzy_search(query, SYMPTOMS, limit=limit)
