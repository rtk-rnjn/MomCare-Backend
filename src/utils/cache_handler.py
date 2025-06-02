from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel, Field
from pymongo import InsertOne, UpdateOne
from pytz import timezone

from src.models import FoodItem, History, MoodHistory, MyPlan, User

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
    from redis.asyncio import Redis

    from .google_api_handler import GoogleAPIHandler

with open("static/foods.txt", "r") as file:
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
        self.misc_collection: AsyncIOMotorCollection[dict[str, Any]] = mongo_client["MomCare"]["misc"]

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

    async def user_exists(self, *, email_address: str) -> bool:
        self.log.debug("Checking if user exists with email: %s", email_address)
        user_id = await self.redis_client.get(f"user:by_email:{email_address}")
        if user_id:
            self.log.info("User exists in Redis for email: %s", email_address)
            return True

        self.log.info("Checking MongoDB for user with email: %s", email_address)
        user = await self.users_collection.find_one({"email_address": email_address})
        if user:
            self.log.debug("User found in MongoDB for email: %s", email_address)
            await self.set_user(user=User(**user))
            return True

        self.log.warning("User not found for email: %s", email_address)
        return False

    async def set_user(self, *, user: User):
        self.log.debug("Setting user in Redis with id: %s", user.id)
        await self.redis_client.set(f"user:{user.id}", user.model_dump_json(), ex=3600)
        await self.redis_client.set(f"user:by_email:{user.email_address}", user.id, ex=3600)
        self.log.info(
            "User set in Redis with id: %s with data: %s",
            user.id,
            user.model_dump_json(),
        )
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

    async def get_food(self, food_name: str) -> Optional[FoodItem]:
        self.log.debug("Getting food by name: %s", food_name)
        food = await self.foods_collection.find_one({"name": food_name})
        if not food:
            self.log.warning("Food not found for name: %s", food_name)
            return None

        food_item = FoodItem(**food)
        image = await self.get_food_image(food_name=food_item.name)
        if image:
            food_item.image_uri = image
        return food_item

    async def create_user(self, *, user: dict) -> None:
        self.log.debug("Creating new user with email: %s", user.get("email_address"))
        await self.users_collection_operations.put(InsertOne(user))
        await self.set_user(user=User(**user))

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone("Asia/Kolkata")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.log.debug("Setting plan in Redis for user id: %s", user_id)
        await self.redis_client.set(
            "plan:%s" % user_id,
            plan.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("Asia/Kolkata")).timestamp()),
        )
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": {"plan": plan.model_dump(mode="json")}},
        )
        await self.users_collection_operations.put(update_operation)

    async def get_plan(self, *, user_id: str):
        self.log.debug("Getting plan for user id: %s", user_id)
        plan_data = await self.redis_client.get(f"plan:{user_id}")  # type: ignore
        if plan_data:
            self.log.info("Plan found in Redis for user id: %s", user_id)
            plan = MyPlan(**json.loads(plan_data))
            if plan.is_empty():
                self.log.warning("Plan is empty for user id: %s", user_id)
                return None
            return plan

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
        mood: Optional[str] = None,
    ) -> List[MoodHistory]:
        # TODO: Implement filtering based on start_date, end_date, and mood
        self.log.debug("Getting mood history for user id: %s", user_id)
        user = await self.get_user(user_id=user_id)
        if not user:
            self.log.warning("User not found for id: %s", user_id)
            return []
        return []

    async def update_user(self, *, user_id: str, updated_user: BaseModel) -> None:
        self.log.debug("Updating user data for id: %s", user_id)
        await self._update_user_cache(user_id=user_id, update_data=updated_user.model_dump(mode="json"))
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": updated_user.model_dump()},
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
        expiration = datetime.now(timezone("Asia/Kolkata")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"tips:{user_id}",
            tips.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("Asia/Kolkata")).timestamp()),
        )
        self.log.info(
            "Tips set in Redis for user id: %s with data: %s",
            user_id,
            tips.model_dump_json(),
        )

    async def get_tips(self, *, user_id: str):
        self.log.debug("Getting tips for user id: %s", user_id)
        tips_data = await self.redis_client.get(f"tips:{user_id}")  # type: ignore
        if tips_data:
            self.log.info("Tips found in Redis for user id: %s", user_id)
            return _TempDailyInsight(**json.loads(tips_data))

        self.log.warning("Tips not found for user id: %s", user_id)
        return None

    async def set_exercise(self, *, user_id: str, exercise: BaseModel) -> None:
        self.log.debug("Setting exercise for user id: %s", user_id)
        expiration = datetime.now(timezone("Asia/Kolkata")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"exercise:{user_id}",
            exercise.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("Asia/Kolkata")).timestamp()),
        )
        self.log.info(
            "Exercise set in Redis for user id: %s with data: %s",
            user_id,
            exercise.model_dump_json(),
        )

    async def get_exercise(self, *, user_id: str) -> Optional[BaseModel]:
        self.log.debug("Getting exercise for user id: %s", user_id)
        exercise_data = await self.redis_client.get(f"exercise:{user_id}")
        if exercise_data:
            self.log.info("Exercise found in Redis for user id: %s", user_id)
            return BaseModel(**json.loads(exercise_data))
        self.log.warning("Exercise not found for user id: %s", user_id)
        return None

    async def get_key_expiry(self, *, key: str) -> Optional[datetime]:
        self.log.debug("Getting key expiry for key: %s", key)
        ttl = await self.redis_client.ttl(key)
        if ttl is not None:
            self.log.info("Key expiry found for key: %s with ttl: %s", key, ttl)
            return datetime.now(timezone("Asia/Kolkata")) + timedelta(seconds=ttl)

        self.log.warning("Key expiry not found for key: %s", key)
        return None

    async def get_song_metadata(self, *, key: str) -> Optional[dict]:
        self.log.debug("Getting song metadata for key: %s", key)
        metadata = await self.redis_client.get(f"song_metadata:{key}")
        if metadata:
            self.log.info("Song metadata found for key: %s", key)
            return json.loads(metadata)

        self.log.info("Song metadata not found in Redis for key: %s. Querying MongoDB...", key)
        song_metadata = await self.misc_collection.find_one(
            {
                "$or": [
                    {"filepath": key},
                    {"title": key},
                    {"artist": key},
                ]
            },
            {"_id": 0, "filepath": 1, "title": 1, "artist": 1, "duration": 1},
        )

        if song_metadata:
            self.log.info("Song metadata found in MongoDB for key: %s", key)
            await self.redis_client.set(f"song_metadata:{key}", json.dumps(song_metadata))
            return song_metadata

        self.log.warning("Song metadata not found for key: %s", key)
        return None

    @staticmethod
    async def background_worker(google_api_handler: GoogleAPIHandler):
        collection = google_api_handler.cache_handler.mongo_client["MomCare"]["users"]
        now = datetime.now(timezone("Asia/Kolkata"))
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        def is_old(date: datetime) -> bool:
            native_date = date.astimezone(timezone("Asia/Kolkata"))
            return native_date < midnight

        async for user_data in collection.find({}):
            user = User(**user_data)

            history = History()
            moods = []
            for mood in user.mood_history:
                if is_old(mood.date):
                    moods.append(mood)

            history.moods = moods

            if user.plan and is_old(user.plan.created_at):
                history.plan = user.plan

            exercises = []
            for exercise in user.exercises:
                if is_old(exercise.assigned_at):
                    exercises.append(exercise)

            history.exercises = exercises

            update_payload = {
                "$addToSet": {
                    "history": history.model_dump(),
                },
                "$pull": {
                    "mood_history": {
                        "date": {"$lt": midnight},
                    },
                    "exercises": {
                        "assigned_at": {"$lt": midnight},
                    },
                },
                "$set": {
                    "plan": MyPlan().model_dump(),
                    "updated_at": now,
                },
            }

            await collection.update_one({"_id": user.id}, update_payload)
