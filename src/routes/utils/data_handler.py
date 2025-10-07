from __future__ import annotations

from random import uniform
from typing import TYPE_CHECKING, Any

from .cache_handler import CacheHandler
from .database_handler import DatabaseHandler
from .hints import ArrayField, FieldType

if TYPE_CHECKING:
    from src.models import User


class DataHandler:
    def __init__(self):
        self.cache_handler = CacheHandler()
        self.database_handler = DatabaseHandler()

        self.redis_client = self.cache_handler.redis_client
        self._key_manager = self.cache_handler._key_manager
        self.users_collection = self.database_handler.users_collection

    async def user_exists(self, email_address: str) -> bool:
        response = await self.redis_client.exists(self._key_manager.user_email_address(email_address))
        if response is None:
            return await self.database_handler.user_exists(email_address)

        return True

    async def create_user(self, user: User) -> bool:
        if self.user_exists(user.email_address):
            return False

        ack = await self.database_handler.insert_user(user)
        if not ack:
            return False

        await self.cache_handler.cache_user(user)
        return True

    async def get_user(self, email: str, password: str) -> User | None:
        user = await self.cache_handler.get_user_by_email(email)
        if user is not None and user.password == password:
            return user

        user = await self.database_handler.fetch_user(email_address=email, password=password)
        if user is not None:
            await self.cache_handler.cache_user(user)
            return user

        return None

    async def get_user_by_id(self, user_id: str, force: bool = False) -> User | None:
        user = await self.cache_handler.get_user_by_id(user_id)
        if user is not None and not force:
            return user

        user = await self.database_handler.fetch_user(id=user_id)
        if user is not None:
            await self.cache_handler.cache_user(user)
            return user

        return None

    async def generate_otp(self, email_address: str) -> str:
        otp = str(int(uniform(100000, 999999)))
        await self.redis_client.set(self._key_manager.otp(email_address), otp, ex=300)
        return otp

    async def verify_otp(self, email_address: str, otp: str) -> bool:
        stored_otp = await self.redis_client.get(self._key_manager.otp(email_address))
        if stored_otp is None:
            return False

        if stored_otp != otp:
            return False

        await self.redis_client.delete(self._key_manager.otp(email_address))
        return True

    async def verify_user(self, *, email_address: str):
        await self.database_handler.update_user(email_address=email_address, set_fields={"is_verified": True})

    async def update_login_meta(self, *, email_address: str, password: str, last_login_ip: str) -> None:
        await self.database_handler.update_login_meta(email_address=email_address, password=password, last_login_ip=last_login_ip)

    async def get_song_metadata(self, /, key: str):
        data = await self.cache_handler.get_song_metadata(key)
        if not data:
            song_metadata = await self.database_handler.fetch_song_metadata(key=key)
            if song_metadata is not None:
                from src.models import SongMetadata

                return SongMetadata.model_validate(song_metadata)

        return data

    async def get_key_expiry(self, /, key: str):
        return await self.cache_handler.get_key_expiry(key)

    async def get_food_image(self, *, food_name: str) -> str | None:
        image_uri = await self.cache_handler.get_food_image(food_name=food_name)
        if image_uri is None:
            from src.app import genai_handler

            image_uri = await genai_handler.fetch_food_image_uri(food_name)

        return image_uri or None

    async def get_food(self, /, food_name: str):
        food = await self.database_handler.fetch_food(food_name)
        if food is None:
            return None

        image = await self.get_food_image(food_name=food.name)
        if image:
            food.image_uri = image
        return food

    async def get_foods(self, /, food_name: str, *, limit: int = 10):
        async for food in self.database_handler.get_foods(food_name, limit=limit):
            image_uri = await self.get_food_image(food_name=food_name)
            food.image_uri = image_uri
            yield food

    async def update_user(
        self,
        email_address: str,
        set_fields: dict[FieldType, Any] | None = None,
        add_to_set: dict[ArrayField, str] | None = None,
        pull_from_set: dict[ArrayField, str] | None = None,
    ):
        return await self.database_handler.update_user(
            email_address=email_address,
            set_fields=set_fields,
            add_to_set=add_to_set,
            pull_from_set=pull_from_set,
        )


data_handler = DataHandler()
