from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

import jwt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from google import genai
from google.genai.types import Content, GenerateContentConfig, Part
from googleapiclient.discovery import build
from pydantic import BaseModel, Field
from pymongo import InsertOne, UpdateOne
from pytz import all_timezones_set, timezone

from src.models import User
from src.models.food_item import FoodItem

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
    from redis.asyncio import Redis

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


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


class Token(BaseModel):
    sub: str
    email: str
    name: str
    iat: int = int(datetime.now(timezone("UTC")).timestamp())
    exp: int


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


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        payload = Token(
            sub=user.id,
            email=user.email_address,
            name=f"{user.first_name} {user.last_name}",
            exp=int((datetime.now(timezone("UTC")) + timedelta(seconds=expire_in)).timestamp()),
        )

        return jwt.encode(dict(payload), self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[Token]:
        try:
            return Token(**jwt.decode(token, self.secret, algorithms=[self.algorithm]))
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def decode_token(self, token: str) -> Optional[Token]:
        try:
            return Token(
                **jwt.decode(
                    token,
                    self.secret,
                    algorithms=[self.algorithm],
                )
            )
        except jwt.InvalidTokenError:
            raise


class _CacheHandler:
    redis_client: Redis
    mongo_client: AsyncIOMotorClient

    users_collection_operations: asyncio.Queue[Union[InsertOne, UpdateOne, None]] = asyncio.Queue()

    def __init__(self, *, mongo_client: AsyncIOMotorClient):
        self.mongo_client = mongo_client
        self.users_collection = mongo_client["MomCare"]["users"]

        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.process_operations())

    async def process_operations(self) -> None:
        while True:
            operation = await self.users_collection_operations.get()
            if operation is None:
                break

            await self.users_collection.bulk_write([operation])

    async def cancel_operations(self) -> None:
        await self.users_collection_operations.put(None)

    def on_startup(self, genai_handler: GoogleAPIHandler) -> List[Callable]:
        async def ping_redis():
            return await self.redis_client.ping()

        async def ping_mongo():
            return await self.mongo_client.admin.command("ping")

        async def start_scheduler():
            scheduler = AsyncIOScheduler()
            scheduler.add_job(CacheHandler.background_worker, "cron", [genai_handler], minute="*")
            scheduler.start()

        return [ping_redis, ping_mongo, start_scheduler]

    def on_shutdown(self) -> List[Callable]:
        async def close_redis():
            await self.redis_client.close()

        async def close_mongo():
            self.mongo_client.close()

        return [close_redis, close_mongo, self.cancel_operations]


class CacheHandler(_CacheHandler):
    def __init__(self, *, redis_client: Redis, mongo_client: AsyncIOMotorClient):
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.users_collection: AsyncIOMotorCollection[dict[str, Any]] = mongo_client["MomCare"]["users"]
        self.foods_collection: AsyncIOMotorCollection[dict[str, Any]] = mongo_client["MomCare"]["foods"]

    async def get_user(
        self, user_id: Optional[str] = None, *, email: Optional[str] = None, password: Optional[str] = None
    ) -> Optional[User]:

        if not (user_id or (email and password)):
            raise ValueError("Either user_id or email and password must be provided")

        if email and password:
            return await self._search_user(email=email, password=password)

        if not user_id:
            raise ValueError("user_id must be provided")

        user = await self.redis_client.hgetall(f"user:{user_id}")  # type: ignore
        if user:
            return User(**user)

        user = await self.users_collection.find_one({"_id": user_id})
        if user:
            return await self.set_user(user=User(**user))

        return None

    async def _search_user(self, *, email: str, password: str) -> Optional[User]:
        user_id = await self.redis_client.get(f"user:by_email:{email}")
        if user_id:
            user = await self.get_user(user_id=user_id)
            if user and user.password == password:
                return user

        user = await self.users_collection.find_one({"email_address": email, "password": password})
        if user:
            return await self.set_user(user=User(**user))

        return None

    async def set_user(self, *, user: User):
        mapped_user = user.model_dump(mode="json")

        await self.redis_client.hset(f"user:{user.id}", mapping=mapped_user)  # type: ignore
        await self.redis_client.expire(f"user:{user.id}", 3600)

        await self.redis_client.set(f"user:by_email:{user.email_address}", user.id, ex=3600)
        await self.redis_client.set(f"user:by_phone:{user.phone_number}", user.id, ex=3600)

        return user

    async def delete_user(self, *, user_id: str) -> None:
        await self.redis_client.delete(f"user:{user_id}", f"user:by_email:{user_id}", f"user:by_phone:{user_id}")

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):
        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            image = await self.get_food_image(food_name=food.name)
            food.image_uri = image.items[0].image.thumbnail_link if image and image.items else ""

            yield food

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.hset(f"plan:{user_id}", mapping=plan.model_dump(mode="json"))  # type: ignore
        await self.redis_client.expire(f"plan:{user_id}", int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()))

    async def get_plan(self, *, user_id: str):
        from src.models.myplan import MyPlan as _MyPlan

        plan = await self.redis_client.hgetall(f"plan:{user_id}")  # type: ignore
        if plan:
            return _MyPlan(**plan)

        return None

    async def set_food_image(self, *, food_name: str, model: RootModel) -> None:
        await self.redis_client.hset(f"food:{food_name}", mapping=model.model_dump(mode="json"))  # type: ignore

    async def get_food_image(self, *, food_name: str) -> Optional[RootModel]:
        image = await self.redis_client.get(f"food:{food_name}")
        if image:
            return RootModel(**image)

        return None

    async def set_tips(self, *, user_id: str, tips: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.hset(f"tips:{user_id}", mapping=tips.model_dump_json())  # type: ignore
        await self.redis_client.expire(f"tips:{user_id}", int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()))

    async def get_tips(self, *, user_id: str):
        tips = await self.redis_client.hgetall(f"tips:{user_id}")  # type: ignore
        if tips:
            return _TempDailyInsight(**tips)

        return None

    @staticmethod
    async def background_worker(google_api_handler: GoogleAPIHandler):
        collection = google_api_handler.cache_handler.mongo_client["MomCare"]["users"]
        UTC_NOW = datetime.now(timezone("UTC"))

        async for user in collection.find({}):
            user_timezone = user.get("timezone", "Asia/Kolkata")

            if user_timezone not in all_timezones_set:
                await asyncio.sleep(0)
                continue

            user_tz = timezone(user_timezone)
            user_now = UTC_NOW.replace(tzinfo=timezone("UTC")).astimezone(user_tz)

            if not (user_now.hour == 0 and user_now.minute == 0):
                continue

            print(f"Processing user: {user['email_address']}")

            history_entry = {
                "date": user_now,
                "plan": user.get("plan"),
                "exercise": user.get("exercises", []),
                "moods": user.get("mood_history", []),
            }

            update_one_operation = UpdateOne(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "mood_history": [],
                        "exercises": [],
                    },
                    "$addToSet": {
                        "history": history_entry,
                    },
                },
            )
            await _CacheHandler.users_collection_operations.put(update_one_operation)


class GoogleAPIHandler:
    def __init__(self, cache_handler: CacheHandler):
        self.gemini_api_key = GEMINI_API_KEY
        self.client = genai.Client(api_key=self.gemini_api_key)
        self.cache_handler = cache_handler

        self.search_service = build("customsearch", "v1", developerKey=os.getenv("GOOGLE_SEARCH_KEY"))

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
                cx=os.getenv("GOOGLE_SEARCH_CX"),
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
