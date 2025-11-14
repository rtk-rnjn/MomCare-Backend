from __future__ import annotations

import hashlib
import os
import pickle
from random import randint
from typing import Awaitable, Callable, Unpack

import arrow
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from redis.asyncio import Redis

from src.models.exercise import ExerciseDict
from src.models.food_item import FoodItemDict
from src.models.mood import MoodDict
from src.models.myplan import MyPlanDict
from src.models.song import SongDict
from src.models.user import UserDict

_ = load_dotenv(verbose=True)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

mongo_client = AsyncIOMotorClient(MONGODB_URI)
database = mongo_client["MomCare"]

DATABASE_NUMBER = 10


class DataHandler:
    def __init__(self):
        self.users_collection: AsyncIOMotorCollection[UserDict] = database["users"]
        self.songs_collection: AsyncIOMotorCollection[SongDict] = database["songs"]
        self.foods_collection: AsyncIOMotorCollection[FoodItemDict] = database["foods"]
        self.myplans_collection: AsyncIOMotorCollection[MyPlanDict] = database["myplans"]
        self.exercises_collection: AsyncIOMotorCollection[ExerciseDict] = database["exercises"]
        self.moods_collection: AsyncIOMotorCollection[MoodDict] = database["moods"]

        self.redis_client = Redis(db=DATABASE_NUMBER, decode_responses=True, protocol=3)

    def _generate_key(self, func, /, *args, **kwargs) -> str:
        raw = [func.__module__, func.__qualname__, args, tuple(sorted(kwargs.items()))]
        data = pickle.dumps(raw, protocol=pickle.HIGHEST_PROTOCOL)
        return hashlib.sha256(data).hexdigest()

    def _parse_payload(self, payload: dict):
        NOT_ALLOWED_FIELDS = {"id", "email_address", "created_at_timestamp", "is_verified"}
        for field in NOT_ALLOWED_FIELDS:
            payload.pop(field, None)

    async def user_exists(self, email_address: str | None, /) -> bool:
        user = await self.users_collection.find_one({"email_address": email_address})
        return user is not None

    async def get_user_timezone(self, user_id: str, /) -> str:
        user = await self.users_collection.find_one({"id": user_id}, {"timezone": 1, "_id": 0})
        if user is None:
            return "Asia/Kolkata"

        return user.get("timezone", "Asia/Kolkata")

    async def create_user(self, **kwargs: Unpack[UserDict]):
        email_address = kwargs.get("email_address")
        if await self.user_exists(email_address):
            return

        return await self.users_collection.insert_one(kwargs)

    async def update_user(self, user_id: str, /, payload: dict):
        self._parse_payload(payload)

        result = await self.users_collection.update_one({"id": user_id}, {"$set": payload})
        return result

    async def get_user(self, *, email_address: str, password: str) -> UserDict | None:
        user = await self.users_collection.find_one({"email_address": email_address, "password": password})
        return user

    async def get_user_by_id(self, user_id: str, /) -> UserDict | None:
        user = await self.users_collection.find_one({"id": user_id}, {"_id": 0})
        return user

    async def generate_otp(self, email_address: str, /) -> str:
        otp = str(randint(100000, 999999))
        key = self._generate_key(self.generate_otp, email_address)
        await self.redis_client.set(key, otp, ex=300)
        return otp

    async def verify_otp(self, email_address: str, otp: str) -> bool:
        key = self._generate_key(self.verify_otp, email_address)

        stored_otp = await self.redis_client.get(key)
        if stored_otp is None:
            return False

        if stored_otp != otp:
            return False

        await self.redis_client.delete(key)
        return True

    async def verify_user(self, /, *, email_address: str):
        await self.users_collection.update_one({"email_address": email_address}, {"$set": {"is_verified": True}})

    async def get_song(self, /, *, song: str):
        data = await self.songs_collection.find_one({"$or": [{"title": song}, {"artist": song}, {"uri": song}]})

        return data

    async def get_key_expiry(self, /, *, key: str) -> int:
        return await self.redis_client.ttl(key)

    async def get_food_image(self, /, *, food_name: str | None, fetch_food_image_uri: Callable[[str], Awaitable[str]]) -> str | None:
        if food_name is None:
            return None

        image_uri = await fetch_food_image_uri(food_name)

        return image_uri or None

    async def get_food(self, food_name: str, /, *, fetch_food_image_uri):
        food = await self.foods_collection.find_one({"name": food_name})
        if food is None:
            return None

        if food.get("image_uri"):
            return food

        image = await self.get_food_image(food_name=food.get("name"), fetch_food_image_uri=fetch_food_image_uri)
        if image:
            food["image_uri"] = image
        return food

    async def get_foods(self, food_name: str, /, *, limit: int = 10, fetch_food_image_uri):
        async for food in self.foods_collection.find({"name": {"$regex": food_name, "$options": "i"}}).limit(limit):
            image_uri = await self.get_food_image(food_name=food.get("name"), fetch_food_image_uri=fetch_food_image_uri)
            food["image_uri"] = image_uri
            yield food

    async def save_myplan(self, plan: MyPlanDict):
        result = await self.myplans_collection.insert_one(plan)
        return result

    async def get_latest_myplan(self, user_id: str) -> MyPlanDict | None:
        plan = await self.myplans_collection.find_one({"user_id": user_id}, sort=[("created_at_timestamp", -1)])
        return plan

    async def get_todays_plan(self, user_id: str) -> MyPlanDict | None:
        tz = await self.get_user_timezone(user_id)
        user_arrow = arrow.utcnow().to(tz)
        start_of_day = user_arrow.floor("day").timestamp()
        end_of_day = user_arrow.ceil("day").timestamp()

        plan = await self.myplans_collection.find_one({"user_id": user_id, "created_at_timestamp": {"$gte": start_of_day, "$lt": end_of_day}})
        return plan

    async def save_exercises(self, exercises: list[ExerciseDict]):
        if not exercises:
            return

        result = await self.exercises_collection.insert_many(exercises)
        return result

    async def get_exercises_by_user(self, user_id: str) -> list[ExerciseDict]:
        exercises = []
        async for exercise in self.exercises_collection.find({"user_id": user_id}):
            exercises.append(exercise)
        return exercises

    async def get_todays_exercises(self, user_id: str) -> list[ExerciseDict]:
        tz = await self.get_user_timezone(user_id)
        user_arrow = arrow.utcnow().to(tz)
        start_of_day = user_arrow.floor("day").timestamp()
        end_of_day = user_arrow.ceil("day").timestamp()

        exercises = []
        async for exercise in self.exercises_collection.find({"user_id": user_id, "assigned_at_timestamp": {"$gte": start_of_day, "$lt": end_of_day}}):
            exercises.append(exercise)
        return exercises

    async def save_mood(self, mood: MoodDict):
        result = await self.moods_collection.insert_one(mood)
        return result


data_handler = DataHandler()
