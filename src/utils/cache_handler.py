from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel, Field
from pymongo import InsertOne, UpdateOne
from pytz import all_timezones_set, timezone

from src.models import User
from src.models.food_item import FoodItem

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
    from redis.asyncio import Redis

    from .google_api_handler import GoogleAPIHandler

with open("foods.txt", "r") as file:
    FOODS = file.read().replace("\n", ",").split(",")


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

        user_data = await self.redis_client.get(f"user:{user_id}")  # type: ignore
        if user_data:
            return User(**json.loads(user_data))

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
        await self.redis_client.set(f"user:{user.id}", user.model_dump_json(), ex=3600)
        await self.redis_client.set(f"user:by_email:{user.email_address}", user.id, ex=3600)

        return user

    async def delete_user(self, *, user_id: str) -> None:
        await self.redis_client.delete(f"user:{user_id}", f"user:by_email:{user_id}")

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):
        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            image = await self.get_food_image(food_name=food.name)
            food.image_uri = image.items[0].image.thumbnail_link if image and image.items else ""

            yield food

    async def create_user(self, *, user: dict) -> None:
        await self.users_collection_operations.put(InsertOne(user))
        await self.set_user(user=User(**user))

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"plan:{user_id}", plan.model_dump_json(), ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp())
        )

    async def get_plan(self, *, user_id: str):
        from src.models.myplan import MyPlan as _MyPlan

        plan_data = await self.redis_client.get(f"plan:{user_id}")  # type: ignore
        if plan_data:
            return _MyPlan(**json.loads(plan_data))

        return None

    async def set_food_image(self, *, food_name: str, model: RootModel) -> None:
        await self.redis_client.set(f"food:{food_name}", model.model_dump_json())  # type: ignore

    async def get_food_image(self, *, food_name: str) -> Optional[RootModel]:
        image = await self.redis_client.get(f"food:{food_name}")
        if image:
            return RootModel(**json.loads(image))

        return None

    async def set_tips(self, *, user_id: str, tips: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"tips:{user_id}", tips.model_dump_json(), ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp())
        )

    async def get_tips(self, *, user_id: str):
        tips_data = await self.redis_client.get(f"tips:{user_id}")  # type: ignore
        if tips_data:
            return _TempDailyInsight(**json.loads(tips_data))

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
