from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai.types import Content, GenerateContentConfig, Part
from googleapiclient.discovery import build
from pydantic import BaseModel, Field

from src.models import User
from src.models.food_item import FoodItem

if TYPE_CHECKING:

    from .cache_handler import CacheHandler

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SEARCH_KEY = os.getenv("SEARCH_API_KEY")

if GOOGLE_SEARCH_KEY is None:
    raise ValueError("GOOGLE_SEARCH_KEY is not set")

if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY is not set")

with open("foods.txt", "r") as file:
    FOODS = file.read().replace("\n", ",").split(",")

CONSTRAINTS = """
Constraints:
- Exclude food items that contain user's intolerances or allergic ingredients.
- Match dietary preferences strictly (e.g., vegetarian, vegan, keto).
- Balance daily calories, protein, carbs, and fat according to standard nutrition practice.
- Ensure variety in vitamin_contents across meals.
- Generate exactly 3-5 items per meal (breakfast, lunch, dinner), and 1-3 for snacks.
- Avoid repetition of same food item in multiple meals.
- Output only valid JSON matching structure above, no text or explanation.
"""


class _TempMyPlan(BaseModel):
    breakfast: List[str] = []
    lunch: List[str] = []
    dinner: List[str] = []
    snacks: List[str] = []


class _TempDailyInsight(BaseModel):
    todays_focus: str
    daily_tip: str


class ImageModel(BaseModel):
    context_link: str = Field(alias="contextLink")
    thumbnail_link: str = Field(alias="thumbnailLink")


class ItemModel(BaseModel):
    title: str
    link: str
    display_link: str = Field(alias="displayLink")
    mime: str
    image: ImageModel


class RootModel(BaseModel):
    items: List[ItemModel]

    class Config:
        validate_by_name = True


class GoogleAPIHandler:
    def __init__(self, cache_handler: CacheHandler):
        self.gemini_api_key = GEMINI_API_KEY
        self.client = genai.Client(api_key=self.gemini_api_key)
        self.cache_handler = cache_handler

        self.search_service = build("customsearch", "v1", developerKey=GOOGLE_SEARCH_KEY)

    async def generate_plan(self, user: User):
        plan = await self.cache_handler.get_plan(user_id=user.id)
        if plan:
            return plan

        user_data = user.model_dump(mode="json")
        user_data.pop("plan")

        plan = await asyncio.to_thread(self._generate_plan, user_data=user_data)
        if not plan:
            return None

        parsed_plan = await self._parse_plan(plan=plan)
        if not parsed_plan:
            return None

        await self.cache_handler.set_plan(user_id=user.id, plan=parsed_plan)
        return parsed_plan

    async def generate_tips(self, user: User):
        tips = await self.cache_handler.get_tips(user_id=user.id)
        if tips:
            return tips

        user_data = user.model_dump(mode="json")
        user_data.pop("plan")

        tips = await self._generate_tips(user=user)
        if not tips:
            return None

        return tips

    def _generate_plan(self, user_data: dict) -> Optional[_TempMyPlan]:
        response = self.client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=[
                Content(
                    parts=[
                        Part.from_text(text=f"User Data: {user_data}"),
                        Part.from_text(text=f"List of available food items: {FOODS}"),
                        Part.from_text(text=f"Today's date: {datetime.now().strftime('%Y-%m-%d')}"),
                    ]
                )
            ],
            config=GenerateContentConfig(
                system_instruction="You are a certified AI dietician. Your role is to generate daily meal plans personalized for users based on their medical history, food intolerances, dietary preferences, mood, and available food items. ",
                response_mime_type="application/json",
                response_schema=_TempMyPlan,
            ),
        )

        if response:
            return _TempMyPlan(**json.loads(response.text or "{}"))

        return None

    async def _parse_plan(self, plan: Optional[_TempMyPlan]):
        if not plan:
            return None

        from src.models.myplan import MyPlan as _MyPlan

        async def fetch_meals(meals):
            if not meals:
                return []

            foods = []
            for meal in meals:
                food = await self.cache_handler.foods_collection.find_one({"name": meal})
                if food:
                    _food = FoodItem(**food)
                    _food.image_uri = await self._generate_food_image_uri(_food.name)
                    _food.consumed = False

                    foods.append(_food)

            return foods

        return _MyPlan(
            breakfast=await fetch_meals(plan.breakfast),
            lunch=await fetch_meals(plan.lunch),
            dinner=await fetch_meals(plan.dinner),
            snacks=await fetch_meals(plan.snacks),
        )

    async def _generate_food_image_uri(self, food_name: str) -> str:
        model = await self._fetch_food_image(food_name)

        if model and model.items:
            image = model.items[0].image
            return image.thumbnail_link

        return ""

    async def _fetch_food_image(self, food_name: str):
        cached_image = await self.cache_handler.get_food_image(food_name=food_name)
        if cached_image:
            return cached_image

        search_response = (
            self.search_service.cse()
            .list(
                q=food_name,
                cx=os.getenv("SEARCH_API_CX"),
                searchType="image",
                num=1,
            )
            .execute()
        )

        root_response = RootModel(**search_response)
        await self.cache_handler.set_food_image(food_name=food_name, model=root_response)
        return root_response

    async def _generate_tips(self, user: User):
        SYSTEM_INSTRUCTION = "Generate a precise and short Daily Tip and Today's Focus for a pregnant woman who is due in October.\n"
        SYSTEM_INSTRUCTION += "Keep it specific to her current pregnancy week based on the due date.\n"
        SYSTEM_INSTRUCTION += "Use 1-2 emojis in each (relevant and appropriate).\n"
        SYSTEM_INSTRUCTION += "Keep wording short, like a daily notification (under 20 words).\n"
        SYSTEM_INSTRUCTION += "Avoid general advice; make it specific to pregnancy week progress.\n"

        response = self.client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=[
                Content(
                    parts=[
                        Part.from_text(text=f"User Data: {user.model_dump(mode='json')}"),
                        Part.from_text(text=f"Today's date: {datetime.now().strftime('%Y-%m-%d')}"),
                    ]
                )
            ],
            config=GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=_TempDailyInsight,
            ),
        )

        if response:
            return _TempDailyInsight(**json.loads(response.text or "{}"))

        return None
