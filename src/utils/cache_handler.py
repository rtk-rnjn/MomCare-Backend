from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel, Field
from pymongo import InsertOne, UpdateOne
from pytz import all_timezones_set, timezone

from src.models import MoodHistory, MoodType, User
from src.models.food_item import FoodItem
from src.models.myplan import MyPlan

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
    thumbnail_link: str = Field(alias="thumbnailLink")


class ItemModel(BaseModel):
    title: str
    link: str
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
        from src.utils.log import log

        self.mongo_client = mongo_client
        self.users_collection = mongo_client["MomCare"]["users"]
        self.log = log

    async def process_operations(self) -> None:
        self.log.info("Starting operation processor")
        while True:
            operation = await self.users_collection_operations.get()
            if operation is None:
                self.log.info("Shutdown signal received for operation processor")
                break

            try:
                await self.users_collection.bulk_write([operation])
                self.log.debug("Processed operation: %s", str(operation))
            except Exception as e:
                self.log.error("Failed to execute bulk operation: %s", str(e))

    async def cancel_operations(self) -> None:
        self.log.info("Cancelling queued operations")
        await self.users_collection_operations.put(None)

    def on_startup(self, genai_handler: GoogleAPIHandler) -> List[Callable]:
        async def ping_redis():
            try:
                result = await self.redis_client.ping()
                self.log.debug("Redis ping result: %s", result)
            except Exception as e:
                self.log.critical("Redis connection failed: %s", str(e))

        async def ping_mongo():
            try:
                result = await self.mongo_client.admin.command("ping")
                self.log.debug("Mongo ping result: %s", result)
            except Exception as e:
                self.log.critical("MongoDB connection failed: %s", str(e))

        async def start_scheduler():
            self.log.info("Starting background scheduler")
            scheduler = AsyncIOScheduler()
            scheduler.add_job(CacheHandler.background_worker, "cron", [genai_handler], minute="*")
            scheduler.start()
            self.log.debug("Scheduler started with cron job")

        async def start_operations():
            self.log.info("Starting async operation queue processor")
            asyncio.create_task(self.process_operations())

        return [ping_redis, ping_mongo, start_scheduler, start_operations]

    def on_shutdown(self) -> List[Callable]:
        async def close_redis():
            self.log.info("Closing Redis connection")
            await self.redis_client.close()

        async def close_mongo():
            self.log.info("Closing MongoDB connection")
            self.mongo_client.close()

        return [close_redis, close_mongo, self.cancel_operations]


class CacheHandler(_CacheHandler):
    def __init__(self, *, redis_client: Redis, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client=mongo_client)

        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.users_collection: AsyncIOMotorCollection[dict[str, Any]] = mongo_client["MomCare"]["users"]
        self.foods_collection: AsyncIOMotorCollection[dict[str, Any]] = mongo_client["MomCare"]["foods"]
        self.log.info("CacheHandler initialized with Redis and MongoDB clients")

    async def get_user(
        self,
        user_id: Optional[str] = None,
        *,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Optional[User]:
        if not (user_id or (email and password)):
            raise ValueError("Either user_id or email and password must be provided")

        if email and password:
            email, password = str(email).lower(), str(password)
            self.log.debug("Searching user by email: %s", email)
            return await self._search_user(email=email, password=password)

        if user_id is None:
            raise ValueError("user_id must be provided")

        if isinstance(user_id, bytes):
            user_id = user_id.decode("utf-8")
        if not isinstance(user_id, str):
            user_id = str(user_id)

        self.log.debug("Attempting to get user from Redis with id: %s", user_id)
        user_data = await self.redis_client.get(f"user:{user_id}")  # type: ignore
        if user_data:
            self.log.info("Cache hit for user id: %s", user_id)
            return User(**json.loads(user_data))

        self.log.info("Cache miss for user id: %s. Querying MongoDB...", user_id)
        user = await self.users_collection.find_one({"_id": user_id})
        if user:
            self.log.debug("User found in MongoDB for id: %s", user_id)
            return await self.set_user(user=User(**user))

        self.log.warning("User not found with id: %s", user_id)
        return None

    async def _search_user(self, *, email: str, password: str) -> Optional[User]:
        user_id = await self.redis_client.get(f"user:by_email:{email}")
        if user_id:
            self.log.info("User ID found in Redis for email: %s", email)
            user = await self.get_user(user_id=user_id)
            if user and user.password == password:
                self.log.debug("Password match for email: %s", email)
                return user
            else:
                self.log.warning("Password mismatch for email: %s", email)

        self.log.info("Looking up MongoDB for email: %s", email)
        user = await self.users_collection.find_one({"email_address": email, "password": password})
        if user:
            self.log.debug("User found in MongoDB for email: %s", email)
            return await self.set_user(user=User(**user))

        self.log.warning("User not found in MongoDB for email: %s", email)
        return None

    async def set_user(self, *, user: User):
        self.log.debug("Setting user in Redis with id: %s", user.id)
        await self.redis_client.set(f"user:{user.id}", user.model_dump_json(), ex=3600)
        await self.redis_client.set(f"user:by_email:{user.email_address}", user.id, ex=3600)
        self.log.info("User set in Redis with id: %s with data: %s", user.id, user.model_dump_json())
        return user

    async def delete_user(self, *, user_id: str) -> None:
        self.log.debug("Deleting user from Redis with id: %s", user_id)
        await self.redis_client.delete(f"user:{user_id}", f"user:by_email:{user_id}")

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):
        self.log.debug("Fetching foods matching name: %s | Fuzzy: %s", food_name, fuzzy_search)
        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            image = await self.get_food_image(food_name=food.name)
            food.image_uri = image
            yield food

    async def create_user(self, *, user: dict) -> None:
        self.log.debug("Creating new user with email: %s", user.get("email_address"))
        await self.users_collection_operations.put(InsertOne(user))
        await self.set_user(user=User(**user))

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.log.debug("Setting plan in Redis for user id: %s", user_id)
        await self.redis_client.set(
            "plan:%s" % user_id,
            plan.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()),
        )
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": {"plan": plan.model_dump(mode="json")}},
        )
        await self.users_collection_operations.put(update_operation)

    async def get_plan(self, *, user_id: str):
        from src.models.myplan import MyPlan as _MyPlan

        self.log.debug("Getting plan for user id: %s", user_id)
        plan_data = await self.redis_client.get(f"plan:{user_id}")  # type: ignore
        if plan_data:
            self.log.info("Plan found in Redis for user id: %s", user_id)
            return _MyPlan(**json.loads(plan_data))

        self.log.warning("No plan found in Redis for user id: %s", user_id)
        return None

    async def set_user_mood(self, *, user_id: str, mood_history: MoodHistory) -> None:
        self.log.debug("Setting mood history for user id: %s", user_id)
        await self._update_user_cache(user_id=user_id, update_data={"mood_history": mood_history})
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": {"mood_history": mood_history.model_dump(mode="json")}},
        )
        await self.users_collection_operations.put(update_operation)

    async def get_user_mood(
        self,
        user_id: str,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        mood: Optional[MoodType] = None,
    ) -> List[MoodHistory]:
        # TODO: Implement filtering based on start_date, end_date, and mood
        self.log.debug("Getting mood history for user id: %s", user_id)
        user = await self.get_user(user_id=user_id)
        if not user:
            self.log.warning("User not found for id: %s", user_id)
            return []
        return []
    
    async def update_user(self, *, user_id: str, update_data: dict) -> None:
        self.log.debug("Updating user data for id: %s", user_id)
        await self._update_user_cache(user_id=user_id, update_data=update_data)
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": update_data},
        )
        await self.users_collection_operations.put(update_operation)

    async def _update_user_cache(self, *, user_id: str, update_data: dict) -> None:
        user = await self.get_user(user_id=user_id)
        if not user:
            return

        self.log.debug("Updating user cache for id: %s", user_id)

        self.log.debug("User: %s data before update: %s", user_id, user.model_dump(mode="json"))
        user_data = user.model_dump(mode="json")
        user_data.update(update_data)
        self.log.debug("User: %s data after update: %s", user_id, user_data)

        self.log.debug("Setting updated user data in Redis for id: %s", user_id)

        plan_data = update_data.get("plan")
        if plan_data:
            plan = MyPlan(**plan_data)
            await self.set_plan(user_id=user_id, plan=plan)

        await self.redis_client.set(f"user:{user_id}", json.dumps(user_data), ex=3600)

    async def set_food_image(self, *, food_name: str, image_link: str) -> None:
        self.log.debug("Setting food image for food: %s", food_name)
        await self.redis_client.set(f"food:{food_name}", image_link)  # type: ignore

    async def get_food_image(self, *, food_name: str) -> Optional[str]:
        self.log.debug("Getting food image for food: %s", food_name)
        image = await self.redis_client.get(f"food:{food_name}")
        if image:
            self.log.info("Food image found for: %s", food_name)
            return image

        self.log.warning("Food image not found for: %s", food_name)
        return None

    async def set_tips(self, *, user_id: str, tips: BaseModel) -> None:
        self.log.debug("Setting tips for user id: %s", user_id)
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"tips:{user_id}",
            tips.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()),
        )
        self.log.info("Tips set in Redis for user id: %s with data: %s", user_id, tips.model_dump_json())

    async def get_tips(self, *, user_id: str):
        self.log.debug("Getting tips for user id: %s", user_id)
        tips_data = await self.redis_client.get(f"tips:{user_id}")  # type: ignore
        if tips_data:
            self.log.info("Tips found in Redis for user id: %s", user_id)
            return _TempDailyInsight(**json.loads(tips_data))

        self.log.warning("Tips not found for user id: %s", user_id)
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
