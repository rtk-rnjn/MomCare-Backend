from __future__ import annotations

import hashlib
import pickle
from random import randint
from typing import Awaitable, Callable, Unpack

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from redis.asyncio import Redis

from src.models.food_item import FoodItemDict
from src.models.song import SongDict
from src.models.user import UserDict

mongo_client = AsyncIOMotorClient("mongodb://localhost:27017")
database = mongo_client["MomCare"]

DATABASE_NUMBER = 10


class DataHandler:
    def __init__(self):
        self.users_collection: AsyncIOMotorCollection[UserDict] = database["users"]
        self.songs_collection: AsyncIOMotorCollection[SongDict] = database["songs"]
        self.foods_collection: AsyncIOMotorCollection[FoodItemDict] = database["foods"]

        self.redis_client = Redis(db=DATABASE_NUMBER, decode_responses=True, protocol=3)

    def _generate_key(self, func, /, *args, **kwargs) -> str:
        raw = [func.__module__, func.__qualname__, args, tuple(sorted(kwargs.items()))]
        data = pickle.dumps(raw, protocol=pickle.HIGHEST_PROTOCOL)
        return hashlib.sha256(data).hexdigest()

    async def user_exists(self, email_address: str | None, /) -> bool:
        user = await self.users_collection.find_one({"email_address": email_address})
        return user is not None

    async def create_user(self, **kwargs: Unpack[UserDict]):
        email_address = kwargs.get("email_address")
        if await self.user_exists(email_address):
            return

        return await self.users_collection.insert_one(kwargs)

    async def get_user(self, *, email_address: str, password: str) -> UserDict | None:
        user = await self.users_collection.find_one({"email_address": email_address, "password": password})
        return user

    async def get_user_by_id(self, user_id: str) -> UserDict | None:
        user = await self.users_collection.find_one({"id": user_id}, {"_id": 0, "password": 0})
        return user

    async def generate_otp(self, email_address: str) -> str:
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

    async def verify_user(self, *, email_address: str):
        await self.users_collection.update_one({"email_address": email_address}, {"$set": {"is_verified": True}})

    async def get_song(self, *, song: str):
        data = await self.songs_collection.find_one({"$or": [{"title": song}, {"artist": song}, {"uri": song}]})

        return data

    async def get_key_expiry(self, /, *, key: str) -> int:
        return await self.redis_client.ttl(key)

    async def get_food_image(self, *, food_name: str | None, fetch_food_image_uri: Callable[[str], Awaitable[str]]) -> str | None:
        if food_name is None:
            return None

        image_uri = await fetch_food_image_uri(food_name)

        return image_uri or None

    async def get_food(self, /, food_name: str, *, fetch_food_image_uri):
        food = await self.foods_collection.find_one({"name": food_name})
        if food is None:
            return None

        if food.get("image_uri"):
            return food

        image = await self.get_food_image(food_name=food.get("name"), fetch_food_image_uri=fetch_food_image_uri)
        if image:
            food["image_uri"] = image
        return food

    async def get_foods(self, /, food_name: str, *, limit: int = 10, fetch_food_image_uri):
        async for food in self.foods_collection.find({"name": {"$regex": food_name, "$options": "i"}}).limit(limit):
            image_uri = await self.get_food_image(food_name=food.get("name"), fetch_food_image_uri=fetch_food_image_uri)
            food.image_uri = image_uri
            yield food


data_handler = DataHandler()
