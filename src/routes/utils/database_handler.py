from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from .hints import ArrayField, FieldType

_ = load_dotenv(verbose=True)
MONGO_URI = os.environ["MONGODB_URI"]

if TYPE_CHECKING:
    from src.models import (
        FoodItem,
        FoodItemDict,
        SongMetadataDict,
        User,
        UserDict,
    )


logger = logging.getLogger(__name__)


class DatabaseHandler:
    def __init__(self):
        self.mongo_client = AsyncIOMotorClient(MONGO_URI)
        self.database = self.mongo_client["MomCare"]

        self.users_collection: AsyncIOMotorCollection[UserDict] = self.database["users"]
        self.foods_collection: AsyncIOMotorCollection[FoodItemDict] = self.mongo_client["MomCare"]["foods"]
        self.misc_collection: AsyncIOMotorCollection[SongMetadataDict] = self.mongo_client["MomCare"]["misc"]

        logger.info("DatabaseHandler initialized and connected to MongoDB")

    async def user_exists(self, email_address: str) -> bool:
        payload = {"email_address": email_address}
        projection = {"_id": 0, "email_address": 1}

        logger.debug("checking if user exists: payload=%s projection=%s", payload, projection)
        user = await self.users_collection.find_one(payload, projection)
        logger.debug("user exists: playload=%s user=%s", payload, user)

        return user is not None

    async def insert_user(self, user: User) -> bool:
        if TYPE_CHECKING:
            user_dict = cast(UserDict, user.model_dump())
        else:
            user_dict = user.model_dump()

        logger.debug("inserting user: %s", user_dict)
        result = await self.users_collection.insert_one(user_dict)

        return result.acknowledged

    async def fetch_user(self, **filter) -> User | None:
        from src.models import User

        logger.debug("fetching user: filter=%s", filter)
        user_dict = await self.users_collection.find_one(filter, {"_id": 0, "history": 0})
        if user_dict is None:
            return None

        logger.debug("fetched user: %s", user_dict)
        return User.model_validate(user_dict)

    async def update_user(
        self,
        email_address: str,
        set_fields: dict[FieldType, Any] | None = None,
        add_to_set: dict[ArrayField, str] | None = None,
        pull_from_set: dict[ArrayField, str] | None = None,
    ) -> bool:
        update_query: dict[str, Any] = {}
        if set_fields:
            update_query["$set"] = set_fields

        if add_to_set:
            update_query["$addToSet"] = add_to_set

        if pull_from_set:
            update_query["$pull"] = pull_from_set

        if not update_query:
            raise ValueError("No fields provided to update")

        logger.debug("updating user: email_address=%s update_query=%s", email_address, update_query)

        result = await self.users_collection.update_one(
            {"email_address": email_address},
            update_query,
        )

        logger.debug("update result: %s", result.raw_result)
        return result.acknowledged and result.modified_count > 0

    async def update_login_meta(self, *, email_address: str, password: str, last_login_ip: str) -> None:
        now = datetime.now(timezone.utc)

        logger.debug("updating login metadata: email_address=%s", email_address)
        await self.users_collection.update_one(
            {
                "email_address": email_address,
                "password": password,
            },
            {"$set": {"last_login": now, "last_login_ip": last_login_ip}},
        )

    async def fetch_song_metadata(self, *, key: str) -> SongMetadataDict | None:
        logger.debug("fetching song metadata: key=%s", key)
        return await self.misc_collection.find_one(
            {
                "$or": [
                    {"filepath": key},
                    {"title": key},
                    {"artist": key},
                ]
            },
            {"_id": 0, "filepath": 1, "title": 1, "artist": 1, "duration": 1},
        )

    async def fetch_food(self, /, food_name: str) -> FoodItem | None:
        logger.debug("fetching food item: food_name=%s", food_name)
        data = await self.foods_collection.find_one({"name": food_name})

        return FoodItem.model_validate(data)

    async def get_foods(self, food_name: str, *, fuzzy_search: bool = True, limit: int = 10):
        logger.debug("getting food items: food_name=%s fuzzy_search=%s limit=%d", food_name, fuzzy_search, limit)
        payload = {"name": food_name}
        if fuzzy_search:
            payload = {"name": {"$regex": food_name, "$options": "i"}}

        async for food in self.foods_collection.find(payload).limit(limit):
            food = FoodItem(**food)
            yield food
