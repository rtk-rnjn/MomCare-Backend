from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, List, Optional, Union

import jwt
from dotenv import load_dotenv
from google import genai
from google.genai.types import Content, GenerateContentConfig, Part
from pydantic import BaseModel
from pymongo import InsertOne, UpdateOne

from src.models import User
from src.models.food_item import FoodItem
from src.models.user import UserMedical

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient
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
    iat: int = int(datetime.now(timezone.utc).timestamp())
    exp: int


class MyPlan(BaseModel):
    breakfast: List[str] = []
    lunch: List[str] = []
    dinner: List[str] = []
    snacks: List[str] = []


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        payload = Token(
            sub=user.id,
            email=user.email_address,
            name=f"{user.first_name} {user.last_name}",
            exp=int((datetime.now(timezone.utc) + timedelta(seconds=expire_in)).timestamp()),
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

    def __init__(self, *, mongo_client: AsyncIOMotorClient):
        self.mongo_client = mongo_client
        self.collection = mongo_client["MomCare"]["users"]

        self.operations: asyncio.Queue[Union[InsertOne, UpdateOne, None]] = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.process_operations())

    async def process_operations(self) -> None:
        while True:
            operation = await self.operations.get()
            if operation is None:
                break

            await self.collection.bulk_write([operation])

    async def cancel_operations(self) -> None:
        await self.operations.put(None)
        await self.loop.shutdown_asyncgens()

    def on_startup(self) -> List[Callable]:
        async def ping_redis():
            return await self.redis_client.ping()

        async def ping_mongo():
            return await self.mongo_client.admin.command("ping")

        return [ping_redis, ping_mongo]

    def on_shutdown(self) -> List[Callable]:
        async def close_redis():
            await self.redis_client.close()

        async def close_mongo():
            self.mongo_client.close()

        return [close_redis, close_mongo]


class CacheHandler(_CacheHandler):
    def __init__(self, *, redis_client: Redis, mongo_client: AsyncIOMotorClient):
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.users_collection = mongo_client["MomCare"]["users"]
        self.foods_collection = mongo_client["MomCare"]["foods"]

    async def get_user(self, user_id: str) -> Optional[User]:
        if user_id == "localhost":
            return self._return_localhost_user()

        user = await self.redis_client.get(user_id)
        if user:
            user = json.loads(user)
            return User(**user)

        user = await self.users_collection.find_one({"_id": user_id})
        if user:
            obj = User(**user)
            await self.redis_client.set(user_id, json.dumps(user), ex=3600)
            return obj

        return None

    async def set_user(self, *, user: User) -> None:
        payload = user.model_dump_json()
        await self.redis_client.set(user.id, payload, ex=3600)

    async def update_user(self, *, user: User) -> None:
        await self.redis_client.delete(user.id)

    async def delete_user(self, *, user_id: str) -> None:
        await self.redis_client.delete(user_id)

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):
        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            yield food

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        await self.redis_client.set(
            f"plan:{user_id}",
            plan.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone.utc).timestamp()),
        )

    async def get_plan(self, *, user_id: str):
        from src.models.myplan import MyPlan as _MyPlan

        plan = await self.redis_client.get(f"plan:{user_id}")
        if plan:
            return _MyPlan(**json.loads(plan))

        return None

    def _return_localhost_user(self) -> User:
        return User(
            id="localhost",
            first_name="Maria",
            last_name="Smith",
            email_address="maria.smith@example.com",
            password="password",
            country_code="US",
            phone_number="1234567890",
            medical_data=UserMedical(
                date_of_birth=datetime(1990, 1, 1),
                height=170,
                pre_pregnancy_weight=70,
                current_weight=77,
                due_date=datetime(2025, 1, 1),
            ),
        )


class GenAIHandler:
    def __init__(self, api_key: Optional[str] = None, *, cache_handler: CacheHandler):
        self.api_key = api_key or GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)
        self.cache_handler = cache_handler

    async def generate_plan(self, user: User):
        plan = await self.cache_handler.get_plan(user_id=user.id)
        if plan:
            return plan

        user_data = user.model_dump(mode="json")
        user_data.pop("plan")

        plan = self._generate_plan(user_data=user_data)
        if not plan:
            return None

        parsed_plan = await self._parse_plan(plan=plan)
        if not parsed_plan:
            return None

        await self.cache_handler.set_plan(user_id=user.id, plan=parsed_plan)
        return parsed_plan

    def _generate_plan(self, user_data: dict) -> Optional[MyPlan]:
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
                response_schema=MyPlan,
            ),
        )

        if response:
            return MyPlan(**json.loads(response.text or "{}"))

        return None

    async def _parse_plan(self, plan: Optional[MyPlan]):
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
                    _food.image_name = ""
                    _food.consumed = False

                    foods.append(_food)

            return foods

        return _MyPlan(
            breakfast=await fetch_meals(plan.breakfast),
            lunch=await fetch_meals(plan.lunch),
            dinner=await fetch_meals(plan.dinner),
            snacks=await fetch_meals(plan.snacks),
        )
