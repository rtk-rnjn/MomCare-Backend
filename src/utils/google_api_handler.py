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

from src.models import MyPlan, User
from src.models.food_item import FoodItem

from .image_generator_handler import ImageGeneratorHandler

if TYPE_CHECKING:

    from .cache_handler import CacheHandler

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SEARCH_KEY = os.getenv("SEARCH_API_KEY")
GOOGLE_SEARCH_CX = os.getenv("SEARCH_API_CX")

if GOOGLE_SEARCH_KEY is None or GOOGLE_SEARCH_CX is None:
    raise ValueError("GOOGLE_SEARCH_KEY or GOOGLE_SEARCH_CX is not set")

if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY is not set")

with open("static/foods.txt", "r") as file:
    FOODS = file.read().replace("\n", ",").split(",")


with open("static/yoga_set.json", "r") as file:
    YOGA_SETS = json.load(file)


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
    targeted_body_parts: List[str]
    week: str
    tags: List[str]


class YogaSets(BaseModel):
    yoga_sets: List[YogaSet] = []


class _TempMyPlan(BaseModel):
    breakfast: List[str] = []
    lunch: List[str] = []
    dinner: List[str] = []
    snacks: List[str] = []


class _TempDailyInsight(BaseModel):
    todays_focus: str
    daily_tip: str


class ImageModel(BaseModel):
    thumbnail_link: str = Field(alias="thumbnailLink")


class ItemModel(BaseModel):
    image: ImageModel


class RootModel(BaseModel):
    items: List[ItemModel]


class GoogleAPIHandler:
    def __init__(self, cache_handler: CacheHandler):
        from src.utils.log import log

        self.gemini_api_key = GEMINI_API_KEY
        self.client = genai.Client(api_key=self.gemini_api_key)
        self.cache_handler = cache_handler
        self.search_service = build("customsearch", "v1", developerKey=GOOGLE_SEARCH_KEY)
        self.log = log

        self.log.info("GoogleAPIHandler initialized with Gemini and Google Custom Search clients.")

        self.image_generator_handler = ImageGeneratorHandler(cache_handler=cache_handler)

    async def generate_plan(self, user: User, *, force_create: bool = False) -> Optional[MyPlan]:
        self.log.info("Generating plan for user ID: %s" % user.id)
        plan = await self.cache_handler.get_plan(user_id=user.id)
        if plan and not force_create:
            self.log.info("Plan found in cache for user ID: %s" % user.id)
            return plan

        user_data = user.model_dump(mode="json")
        user_data.pop("plan", None)

        self.log.info("Calling Gemini API to generate plan for user ID: %s" % user.id)
        plan = await asyncio.to_thread(self._generate_plan, user_data=user_data)
        if not plan:
            self.log.warning("Gemini API returned no plan for user ID: %s" % user.id)
            return None

        parsed_plan = await self._parse_plan(plan=plan)
        if not parsed_plan:
            self.log.warning("Failed to parse plan for user ID: %s" % user.id)
            return None

        await self.cache_handler.set_plan(user_id=user.id, plan=parsed_plan)
        self.log.info("Plan generated and cached for user ID: %s" % user.id)
        return parsed_plan

    async def generate_tips(self, user: User):
        self.log.info("Generating tips for user ID: %s" % user.id)
        tips = await self.cache_handler.get_tips(user_id=user.id)
        if tips:
            self.log.info("Tips found in cache for user ID: %s" % user.id)
            return tips

        user_data = user.model_dump(mode="json")
        user_data.pop("plan", None)

        self.log.info("Calling Gemini API to generate tips for user ID: %s" % user.id)
        tips = await self._generate_tips(user=user)
        if not tips:
            self.log.warning("Gemini API returned no tips for user ID: %s" % user.id)
            return None

        self.log.info("Tips generated for user ID: %s" % user.id)
        return tips

    def _generate_plan(self, user_data: dict) -> Optional[_TempMyPlan]:
        user_data.pop("history", None)
        user_data.pop("mood_history", None)
        user_data.pop("exercises", None)

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-001",
                contents=[
                    Content(
                        parts=[
                            Part.from_text(text=f"User Data: {user_data}"),
                            Part.from_text(text=f"List of available food items: {FOODS}"),
                            Part.from_text(text="Today's date: {}".format(datetime.now().strftime("%Y-%m-%d"))),
                        ]
                    )
                ],
                config=GenerateContentConfig(
                    system_instruction="""
                You are a certified AI dietician. Your role is to generate daily meal plans personalized for pregnant users based on their medical history, food intolerances, dietary preferences, mood, available food items, and their current pregnancy stage.

                First, determine the user's day, week, and trimester based on their due date or conception information. Use this to define today's specific nutritional goal based on fetal development needs and maternal health at that stage.

                Generate a meal plan that:
                - Aligns with that goal.
                - Is diverse and non-repetitive—do not repeat any meal within the same week.
                - Considers what meals have already been suggested to the user in the past.
                - Incorporates available food items to ensure feasibility.
                - Reflects user's mood if applicable (e.g., comfort foods during emotional days, light meals during nausea).

                Continuously adapt each day’s plan based on prior meal suggestions and changes in the user’s health, food preferences, or inventory.
                """,
                    response_mime_type="application/json",
                    response_schema=_TempMyPlan,
                ),
            )

            if response:
                return _TempMyPlan(**json.loads(response.text or "{}"))
        except Exception as e:
            self.log.error("Error generating plan with Gemini API: %s" % str(e), exc_info=True)

        return None

    async def _parse_plan(self, plan: Optional[_TempMyPlan]):
        if not plan:
            self.log.warning("Empty plan received in _parse_plan.")
            return None

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
                else:
                    self.log.warning("Food item '%s' not found in collection." % meal)

            return foods

        self.log.info("Parsing plan and fetching food images.")
        return MyPlan(
            breakfast=await fetch_meals(plan.breakfast),
            lunch=await fetch_meals(plan.lunch),
            dinner=await fetch_meals(plan.dinner),
            snacks=await fetch_meals(plan.snacks),
        )

    async def _generate_food_image_uri(self, food_name: str) -> str:
        image = await self._fetch_food_image(food_name)
        if image:
            return image

        self.log.warning("No image found for food: %s" % food_name)
        return ""

    async def _fetch_food_image(self, food_name: str) -> Optional[str]:
        cached_image = await self.cache_handler.get_food_image(food_name=food_name)
        if cached_image:
            self.log.info("Image for '%s' retrieved from cache." % food_name)
            return cached_image

        self.log.info("Fetching image for '%s' from Google Search." % food_name)
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
            await self.cache_handler.set_food_image(food_name=food_name, image_link=image_link)
            self.log.info("Image for '%s' fetched and cached." % food_name)
            return image_link

        except Exception as e:
            self.log.error("Error fetching image for '%s': %s" % (food_name, str(e)), exc_info=True)

        pixel_image_uri = await self.image_generator_handler.search_image(food_name=food_name)
        if pixel_image_uri:
            return pixel_image_uri

    async def _generate_tips(self, user: User):
        SYSTEM_INSTRUCTION = "Generate a precise and short Daily Tip and Today's Focus for a pregnant woman who is due in October.\n"
        SYSTEM_INSTRUCTION += "Keep it specific to her current pregnancy week based on the due date.\n"
        SYSTEM_INSTRUCTION += "Use 1-2 emojis in each (relevant and appropriate).\n"
        SYSTEM_INSTRUCTION += "Keep wording short, like a daily notification (under 20 words).\n"
        SYSTEM_INSTRUCTION += "Avoid general advice; make it specific to pregnancy week progress.\n"

        user_data = user.model_dump(mode="json")

        user_data.pop("history", None)
        user_data.pop("plan", None)
        user_data.pop("mood_history", None)

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
                    response_schema=_TempDailyInsight,
                ),
            )

            if response:
                tips = _TempDailyInsight(**json.loads(response.text or "{}"))
                await self.cache_handler.set_tips(user_id=user.id, tips=tips)
                return tips

        except Exception as e:
            self.log.error("Error generating tips: %s" % str(e), exc_info=True)

        return None

    async def _get_exercise(self, user: User):
        SYSTEM_INSTRUCTION = "Suggest what exercise should a pregnant woman do today.\n"
        SYSTEM_INSTRUCTION += "Keep it specific to her current pregnancy week based on the due date.\n"
        SYSTEM_INSTRUCTION += "Avaiable yoga sets: {}\n".format(
            [YogaSet(**yoga_set).model_dump(mode="json") for yoga_set in YOGA_SETS]
        )

        user_data = user.model_dump(mode="json")

        user_data.pop("history", None)
        user_data.pop("plan", None)
        user_data.pop("mood_history", None)
        user_data.pop("exercises", None)

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
                await self.cache_handler.set_exercise(user_id=user.id, exercise=exercise)
                return exercise

        except Exception as e:
            self.log.error("Error generating exercise: %s" % str(e), exc_info=True)
        return None

    async def get_exercises(self, user: User):
        self.log.info("Generating exercise for user ID: %s" % user.id)
        exercise = await self.cache_handler.get_exercise(user_id=user.id)
        if exercise:
            self.log.info("Exercise found in cache for user ID: %s" % user.id)
            return exercise

        self.log.info("Calling Gemini API to generate exercise for user ID: %s" % user.id)
        exercise = await self._get_exercise(user=user)
        if not exercise:
            self.log.warning("Gemini API returned no exercise for user ID: %s" % user.id)
            return None

        self.log.info("Exercise generated for user ID: %s" % user.id)
        return exercise
