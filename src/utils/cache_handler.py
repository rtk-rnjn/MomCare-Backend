from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, List, Optional, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field
from pymongo import InsertOne, UpdateOne
from pytz import timezone

from src.models import FoodItem, History, MyPlan, User, UserMedical

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from src.models import FoodItemDict, SongMetadataDict, UserDict

    from .google_api_handler import GoogleAPIHandler

with open("static/foods.txt", "r") as file:
    FOODS = file.read().replace("\n", ",").split(",")


class YogaSet(BaseModel):
    name: str
    level: str
    description: str
    targeted_body_parts: List[str]
    week: str
    tags: List[str]


class YogaSets(BaseModel):
    yoga_sets: List[YogaSet] = []


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


class _CacheHandler:
    redis_client: Redis
    mongo_client: AsyncIOMotorClient

    users_collection_operations: asyncio.Queue[Union[InsertOne, UpdateOne, None]] = asyncio.Queue()

    def __init__(self, *, mongo_client: AsyncIOMotorClient):
        self.mongo_client = mongo_client
        self.users_collection: AsyncIOMotorCollection[UserDict] = mongo_client["MomCare"]["users"]

    async def process_operations(self) -> None:

        while True:
            operation = await self.users_collection_operations.get()
            if operation is None:
                break

            try:
                await self.users_collection.bulk_write([operation])
            except Exception:
                pass

    async def cancel_operations(self) -> None:
        await self.users_collection_operations.put(None)

    async def on_startup(self, genai_handler: GoogleAPIHandler):
        async def ping_redis():
            await self.redis_client.ping()

        async def ping_mongo():
            await self.mongo_client.admin.command("ping")

        async def start_scheduler():

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                CacheHandler.background_worker,
                "cron",
                [genai_handler],
                minute="*",
                id="background_worker",
            )
            scheduler.start()

        async def start_operations():

            asyncio.create_task(self.process_operations())

        await asyncio.gather(
            ping_redis(),
            ping_mongo(),
            start_scheduler(),
            start_operations(),
        )

    async def on_shutdown(self):
        async def close_redis():
            await self.redis_client.close()

        async def close_mongo():
            self.mongo_client.close()

        async def cancel_operations():
            await self.cancel_operations()

        await asyncio.gather(
            close_redis(),
            close_mongo(),
            cancel_operations(),
        )


class CacheHandler(_CacheHandler):
    def __init__(self, *, redis_client: Optional[Redis] = None, mongo_client: Optional[AsyncIOMotorClient] = None):
        if mongo_client is None:
            mongo_client = AsyncIOMotorClient(tz_aware=True)

        super().__init__(mongo_client=mongo_client)

        if redis_client is None:
            from redis.asyncio import Redis

            redis_client = Redis(decode_responses=True)

        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.users_collection: AsyncIOMotorCollection[UserDict] = mongo_client["MomCare"]["users"]
        self.foods_collection: AsyncIOMotorCollection[FoodItemDict] = mongo_client["MomCare"]["foods"]
        self.misc_collection: AsyncIOMotorCollection[SongMetadataDict] = mongo_client["MomCare"]["misc"]

    async def get_user(
        self,
        user_id: Optional[str] = None,
        *,
        email: Optional[str] = None,
        password: Optional[str] = None,
        force: bool = False,
    ) -> Optional[User]:
        if not (user_id or (email and password)):
            raise ValueError("Either user_id or email and password must be provided")

        if email and password:
            email, password = str(email).lower(), str(password)

            return await self._search_user(email=email, password=password)

        if user_id is None:
            raise ValueError("user_id must be provided")

        if isinstance(user_id, bytes):
            user_id = user_id.decode("utf-8")
        if not isinstance(user_id, str):
            user_id = str(user_id)

        if not force:

            user_data = await self.redis_client.get(f"user:{user_id}")  # type: ignore
            if user_data:

                return User(**json.loads(user_data))

        user_data = await self.users_collection.find_one({"_id": user_id})
        if user_data is not None:
            user = CacheHandler.from_dict(user_data)
            return await self.set_user(user=user)

        return None

    async def __get_user_id_by_email(self, email: str) -> Optional[str]:

        user_id = await self.redis_client.get(f"user:by_email:{email}")
        if user_id:

            return user_id.decode("utf-8") if isinstance(user_id, bytes) else user_id

        user = await self.users_collection.find_one({"email_address": email})
        if user is not None:

            return user["id"]

        return None

    async def _search_user(self, *, email: str, password: str) -> Optional[User]:
        user_id = await self.redis_client.get(f"user:by_email:{email}")
        if user_id:
            user = await self.get_user(user_id=user_id)
            if user and user.password == password:

                return user

        user_data = await self.users_collection.find_one({"email_address": email, "password": password})
        if user_data is not None:
            user = CacheHandler.from_dict(user_data)
            return await self.set_user(user=user)

        return None

    async def user_exists(self, *, email_address: str) -> bool:
        user_id = await self.redis_client.get(f"user:by_email:{email_address}")
        if user_id:

            return True

        user_data = await self.users_collection.find_one({"email_address": email_address})
        if user_data is not None:
            user = CacheHandler.from_dict(user_data)
            await self.set_user(user=user)
            return True

        return False

    async def set_user(self, *, user: User):
        await self.redis_client.set(f"user:{user.id}", user.model_dump_json(), ex=300)
        await self.redis_client.set(f"user:by_email:{user.email_address}", user.id, ex=300)

        return user

    async def factory_delete_user(self, *, user_id: Optional[str], email_address: Optional[str] = None) -> None:
        await self.redis_client.delete(
            f"user:{user_id}",
            f"user:by_email:{email_address}",
            f"plan:{user_id}",
            # f"tips:{user_id}",
            f"exercise:{user_id}",
        )

    async def refresh_cache(self, *, user_id: Optional[str] = None, email_address: Optional[str] = None) -> None:
        await self.redis_client.publish("cache_refresh", str(user_id))
        await self.factory_delete_user(user_id=user_id, email_address=email_address)

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):

        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            image = await self.get_food_image(food_name=food.name)
            food.image_uri = image
            yield food

    async def get_food(self, food_name: str) -> Optional[FoodItem]:

        food = await self.foods_collection.find_one({"name": food_name})
        if not food:

            return None

        food_item = FoodItem(**food)
        image = await self.get_food_image(food_name=food_item.name)
        if image:
            food_item.image_uri = image
        return food_item

    async def create_user(self, *, user: dict) -> None:

        await self.users_collection_operations.put(InsertOne(user))
        await self.set_user(user=User(**user))

    async def set_plan(self, *, user_id: str, plan: BaseModel) -> None:
        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        await self.redis_client.set(
            "plan:%s" % user_id,
            plan.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()),
        )
        update_operation = UpdateOne(
            {"_id": user_id},
            {"$set": {"plan": plan.model_dump()}},
        )
        await self.users_collection_operations.put(update_operation)

    async def get_plan(self, *, user_id: str):

        plan_data = await self.redis_client.get(f"plan:{user_id}")  # type: ignore
        if plan_data:

            plan = MyPlan(**json.loads(plan_data))
            if plan.is_empty():

                return None
            return plan

        user = await self.get_user(user_id=user_id, force=True)
        if user and user.plan:

            if user.plan.is_old() or user.plan.is_empty():

                return None
            return user.plan

        return None

    async def update_user(
        self,
        *,
        user_id: Optional[str] = None,
        email_address: Optional[str] = None,
        updated_user: Union[BaseModel, dict],
        **extra_fields: dict[str, Any],
    ) -> None:

        update_operation = UpdateOne(
            {
                "$or": [
                    {"_id": user_id},
                    {"email_address": email_address},
                ]
            },
            {
                "$set": {
                    **(updated_user if isinstance(updated_user, dict) else updated_user.model_dump()),
                    "updated_at": datetime.now(timezone("UTC")),
                    **extra_fields,
                }
            },
        )

        await self.users_collection_operations.put(update_operation)
        await self.refresh_cache(user_id=user_id, email_address=email_address)

    async def set_food_image(self, *, food_name: str, image_link: str) -> None:

        await self.redis_client.set(f"food:{food_name}", image_link)  # type: ignore

    async def get_food_image(self, *, food_name: str) -> Optional[str]:

        image = await self.redis_client.get(f"food:{food_name}")
        if image:

            return image

        return None

    async def set_tips(self, *, user_id: str, tips: BaseModel) -> None:

        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"tips:{user_id}",
            tips.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()),
        )

    async def get_tips(self, *, user_id: str):

        tips_data = await self.redis_client.get(f"tips:{user_id}")  # type: ignore
        if tips_data:

            return _TempDailyInsight(**json.loads(tips_data))

        return None

    async def set_exercise(self, *, user_id: str, exercise: BaseModel) -> None:

        expiration = datetime.now(timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await self.redis_client.set(
            f"exercise:{user_id}",
            exercise.model_dump_json(),
            ex=int(expiration.timestamp() - datetime.now(timezone("UTC")).timestamp()),
        )

    async def get_exercises(self, *, user_id: str) -> Optional[YogaSets]:

        exercise_data = await self.redis_client.get(f"exercise:{user_id}")
        if exercise_data:

            return YogaSets(**json.loads(exercise_data))

        return None

    async def get_key_expiry(self, *, key: str) -> Optional[datetime]:

        ttl = await self.redis_client.ttl(key)
        if ttl is not None:

            return datetime.now(timezone("UTC")) + timedelta(seconds=ttl)

        return None

    async def get_song_metadata(self, *, key: str) -> Optional[SongMetadataDict]:

        metadata = await self.redis_client.get(f"song_metadata:{key}")
        if metadata:

            return json.loads(metadata)

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

            await self.redis_client.set(f"song_metadata:{key}", json.dumps(song_metadata))
            return song_metadata

        return None

    def _generate_otp(self) -> str:

        otp = str(random.randint(100000, 999999))

        return otp

    async def generate_otp(self, *, email_address: str) -> str:

        otp = self._generate_otp()
        await self.redis_client.set(f"otp:{email_address}", otp, ex=300)

        return otp

    async def verify_otp(self, *, email_address: str, otp: str) -> bool:

        stored_otp = await self.redis_client.get(f"otp:{email_address}")
        if stored_otp and stored_otp == otp:

            await self.redis_client.delete(f"otp:{email_address}")
            return True

        return False

    @staticmethod
    async def background_worker(google_api_handler: GoogleAPIHandler):

        collection = google_api_handler.cache_handler.mongo_client["MomCare"]["users"]

        def is_old(date: datetime) -> bool:
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone("UTC"))

            now = datetime.now(timezone("UTC"))
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return date < midnight

        async for user_data in collection.find({}):
            user = User(**user_data)

            history = History(plan=None)
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
            if history.is_empty():
                continue

            now = datetime.now(timezone("UTC"))
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

            history.date = midnight

            update_payload = {
                "$addToSet": {
                    "history": {"$each": [history.model_dump()]},
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
            await google_api_handler.cache_handler.refresh_cache(user_id=user.id)

    @staticmethod
    def from_dict(data: UserDict) -> User:
        medical_data = data.get("medical_data")
        if medical_data is not None:
            user_medical = UserMedical(
                date_of_birth=medical_data["date_of_birth"],
                due_date=medical_data["due_date"],
                height=medical_data["height"],
                current_weight=medical_data["current_weight"],
                pre_existing_conditions=medical_data["pre_existing_conditions"],
                food_intolerances=medical_data["food_intolerances"],
                dietary_preferences=medical_data["dietary_preferences"],
                pre_pregnancy_weight=medical_data["pre_pregnancy_weight"],
            )
        else:
            user_medical = None

        user = User(
            id=data["id"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email_address=data["email_address"],
            password=data["password"],
            country=data["country"],
            country_code=data["country_code"],
            phone_number=data["phone_number"],
            medical_data=user_medical,
            last_login=data.get("last_login"),
            updated_at=data.get("updated_at"),
            last_login_ip=data.get("last_login_ip"),
        )
        return user
