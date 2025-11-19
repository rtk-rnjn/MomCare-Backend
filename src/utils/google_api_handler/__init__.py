from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai.types import Content, GenerateContentConfig, Part
from googleapiclient.discovery import build
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field

from src.models.food_item import FoodItemDict as FoodItem
from src.models.myplan import MyPlanDict as MyPlan
from src.models.user import UserDict as User

from ..image_generator_handler import PixabayImageFetcher

_ = load_dotenv(verbose=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SEARCH_KEY = os.getenv("SEARCH_API_KEY")
GOOGLE_SEARCH_CX = os.getenv("SEARCH_API_CX")

if GOOGLE_SEARCH_KEY is None or GOOGLE_SEARCH_CX is None:
    raise ValueError("GOOGLE_SEARCH_KEY or GOOGLE_SEARCH_CX is not set")

if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY is not set")

with open("src/static/foods.txt", "r") as file:
    FOODS = file.read().replace("\n", ",").split(",")


with open("src/static/yoga_set.json", "r") as file:
    YOGA_SETS: list[dict] = json.load(file)

with open("src/utils/google_api_handler/diet_plan_prompt.txt") as file:
    DIET_PLAN_PROMPT = file.read()

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


class YogaSet(BaseModel):
    name: str
    level: str
    description: str
    targeted_body_parts: list[str]
    week: str
    tags: list[str]


class YogaSets(BaseModel):
    yoga_sets: list[YogaSet] = []


class PartialMyPlan(BaseModel):
    breakfast: list[str] = []
    lunch: list[str] = []
    dinner: list[str] = []
    snacks: list[str] = []


class DailyInsight(BaseModel):
    todays_focus: str
    daily_tip: str


class ImageModel(BaseModel):
    thumbnail_link: str = Field(alias="thumbnailLink")


class ItemModel(BaseModel):
    image: ImageModel


class RootModel(BaseModel):
    items: list[ItemModel]


class GoogleAPIHandler:
    def __init__(self):

        self.gemini_api_key = GEMINI_API_KEY
        self.client = genai.Client(api_key=self.gemini_api_key)
        self.search_service = build("customsearch", "v1", developerKey=GOOGLE_SEARCH_KEY)

        self.image_generator_handler = PixabayImageFetcher()

    async def generate_plan(self, user: User, *, foods_collection: AsyncIOMotorCollection):
        user_data = user
        user_data.pop("plan", None)
        user_data.pop("_id", None)

        plan = await asyncio.to_thread(self._generate_plan, user_data=user_data)
        if not plan:
            raise Exception("Failed to generate plan")

        parsed_plan = await self._parse_plan(plan=plan, foods_collection=foods_collection)
        if parsed_plan is None:
            raise Exception("Failed to parse plan")

        return parsed_plan

    async def generate_tips(self, user: User):
        user_data = user
        user_data.pop("plan", None)

        tips = await self._generate_tips(user=user)
        if tips is None:

            return None

        return tips

    def _generate_plan(self, user_data: User) -> PartialMyPlan | None:
        plan_history = None

        response = self.client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=[
                Content(
                    parts=[
                        Part.from_text(text=f"User Data: {user_data}"),
                        Part.from_text(text=f"User Plan History: {plan_history if plan_history else 'No previous plans found.'}"),
                        Part.from_text(text=f"List of available food items: {FOODS}"),
                        Part.from_text(text="Today's date: {}".format(datetime.now().strftime("%Y-%m-%d"))),
                    ]
                )
            ],
            config=GenerateContentConfig(
                system_instruction=DIET_PLAN_PROMPT,
                response_mime_type="application/json",
                response_schema=PartialMyPlan,
            ),
        )

        if response:
            return PartialMyPlan(**json.loads(response.text or "{}"))

    async def _parse_plan(self, *, plan: PartialMyPlan | None, foods_collection: AsyncIOMotorCollection) -> MyPlan | None:
        if not plan:
            return None

        async def fetch_meals(meals: list[str]) -> list[FoodItem]:
            if not meals:
                return []

            foods = []
            for meal in meals:
                food_data = await foods_collection.find_one({"name": meal})
                if food_data:
                    food = FoodItem(**food_data)
                    food["image_uri"] = await self.fetch_food_image_uri(food.get("name"))
                    food["consumed"] = False
                    foods.append(food)

            return foods

        return MyPlan(
            breakfast=await fetch_meals(plan.breakfast),
            lunch=await fetch_meals(plan.lunch),
            dinner=await fetch_meals(plan.dinner),
            snacks=await fetch_meals(plan.snacks),
        )

    async def fetch_food_image_uri(self, food_name: str | None) -> str:
        if food_name is None:
            return ""

        image = await self._fetch_food_image(food_name)
        if image:
            return image

        return ""

    async def _fetch_food_image(self, food_name: str) -> str | None:
        try:
            cse = await asyncio.to_thread(self.search_service.cse)
            prepare_list = await asyncio.to_thread(
                cse.list,
                q=f"{food_name} - HD Food Image",
                cx=GOOGLE_SEARCH_CX,
                searchType="image",
                num=1,
            )
            search_response = await asyncio.to_thread(prepare_list.execute)

            root_response = RootModel(**search_response)
            image_link = root_response.items[0].image.thumbnail_link
            return image_link

        except Exception:

            pixel_image_uri = await self.image_generator_handler.search_image(food_name=food_name)
            if pixel_image_uri:
                return pixel_image_uri

    async def _generate_tips(self, user: User):
        SYSTEM_INSTRUCTION = "Generate a precise and short Daily Tip and Today's Focus for a pregnant woman who is due in October.\n"
        SYSTEM_INSTRUCTION += "Keep it specific to her current pregnancy week based on the due date.\n"
        SYSTEM_INSTRUCTION += "Use 1-2 emojis in each (relevant and appropriate).\n"
        SYSTEM_INSTRUCTION += "Keep wording short, like a daily notification (under 20 words).\n"
        SYSTEM_INSTRUCTION += "Avoid general advice; make it specific to pregnancy week progress.\n"

        user_data = user

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-001",
                contents=[
                    Content(
                        parts=[
                            Part.from_text(text="User Data: {}".format(user_data)),
                            Part.from_text(text="Today's date: {}".format(datetime.now().strftime("%Y-%m-%d"))),
                        ]
                    )
                ],
                config=GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=DailyInsight,
                ),
            )

            if response:
                tips = DailyInsight(**json.loads(response.text or "{}"))
                return tips

        except Exception:

            return None

    async def _get_exercises(self, user: User):
        SYSTEM_INSTRUCTION = "Suggest what exercise should a pregnant woman do today.\n"
        SYSTEM_INSTRUCTION += "Keep it specific to her current pregnancy week based on the due date. 4-5 Exercises would be enough.\n"
        SYSTEM_INSTRUCTION += "Avaiable yoga sets: {}\n".format(
            [YogaSet(**yoga_set).model_dump(mode="json") for yoga_set in YOGA_SETS]
        )

        user_data = user

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-001",
                contents=[
                    Content(
                        parts=[
                            Part.from_text(text="User Data: {}".format(user_data)),
                            Part.from_text(text="Today's date: {}".format(datetime.now().strftime("%Y-%m-%d"))),
                        ]
                    )
                ],
                config=GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=YogaSets,
                ),
            )

            if response:
                exercise = YogaSets(**json.loads(response.text or "{}"))
                return exercise

        except Exception:
            return None

    async def get_exercises(self, user: User):
        exercise = await self._get_exercises(user=user)
        if not exercise:
            return None

        return exercise
