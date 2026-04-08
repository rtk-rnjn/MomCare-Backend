from __future__ import annotations

import json
import os
import threading
import time
from string import Template
from typing import Any, TypedDict, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai.types import Content, GenerateContentConfig, Part
from pydantic import BaseModel, Field

from src.models import ExerciseModel, PartialMyPlanModel
from src.models import UserDict as User

load_dotenv()


class ExercisesModel(BaseModel):
    exercises: list[ExerciseModel]


class DailyInsightModel(BaseModel):
    todays_focus: str = Field(..., description="The main focus for the day.", title="Today's Focus")
    daily_tip: str = Field(..., description="A helpful tip for the day.", title="Daily Tip")

    class Config:
        extra = "ignore"


class Data(TypedDict):
    system: str
    user: list[str]


class PromptsDict(TypedDict):
    tips_prompt: Data
    exercise_prompt: Data
    plan_prompt: Data


with open("src/utils/prompts.json", "r") as f:
    PROMPTS: PromptsDict = json.load(f)

ModelT = TypeVar("ModelT", bound=BaseModel)


class GoogleAPIHandler:
    def __init__(self):
        key_seperator = os.environ["GEMINI_API_KEY_SEPERATOR"]
        self.__keys = os.environ["GEMINI_API_KEYS"].split(key_seperator)

        if not self.__keys:
            raise ValueError("No GEMINI API keys provided")

        self.__index = 0
        self.__lock = threading.Lock()

        self.model = "gemini-2.5-flash"

    def _next_key(self) -> str:
        with self.__lock:
            key = self.__keys[self.__index]
            self.__index = (self.__index + 1) % len(self.__keys)
            return key

    async def _generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: list[str],
        response_schema: type[ModelT],
    ) -> ModelT:
        client = genai.Client(api_key=self._next_key())
        content = Content(parts=[Part.from_text(text=part) for part in user_prompt])
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            tools=[],
        )
        model = self.model
        response = await client.aio.models.generate_content(
            model=model,
            contents=[content],
            config=config,
        )
        if response.text:
            return response_schema(**json.loads(response.text))

        return response_schema()

    async def generate_tips(self, user: User):
        system_prompt = PROMPTS["tips_prompt"]["system"]
        user_prompt = PROMPTS["tips_prompt"]["user"]

        user_prompt = [Template(part).safe_substitute(user=user, todays_timestamp=time.time()) for part in user_prompt]

        tips = await self._generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=DailyInsightModel,
        )
        return tips

    async def generate_exercises(self, user: User, exercise_sets: list[dict]):
        system_prompt = PROMPTS["exercise_prompt"]["system"]
        user_prompt = PROMPTS["exercise_prompt"]["user"]

        user_prompt = [Template(part).safe_substitute(user=user, todays_timestamp=time.time()) for part in user_prompt]
        system_prompt = Template(system_prompt).safe_substitute(exercise_sets=exercise_sets)

        routine = await self._generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=ExercisesModel,
        )
        return routine

    async def generate_plan(self, user: User, available_foods: list[dict[str, Any]]):
        system_prompt = PROMPTS["plan_prompt"]["system"]
        user_prompt = PROMPTS["plan_prompt"]["user"]

        user_prompt = [
            Template(part).safe_substitute(
                user=user,
                todays_timestamp=time.time(),
                available_food_items=available_foods,
                past_meal_plans=[],
            )  # TODO: pass in past meal plans
            for part in user_prompt
        ]

        generated = await self._generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=PartialMyPlanModel,
        )
        return generated
