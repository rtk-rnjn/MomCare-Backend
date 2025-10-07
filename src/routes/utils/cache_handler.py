from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pytz import timezone
from redis.asyncio import Redis

from .redis_key_manager import RedisKeyManager

if TYPE_CHECKING:
    from database_handler import ArrayField, FieldType, UserField

    from src.models import SongMetadata, SongMetadataDict, User


class CacheHandler:
    def __init__(self):
        self._key_manager = RedisKeyManager()
        self.redis_client = Redis(db=1, decode_responses=True, protocol=3)

    async def close(self):
        await self.redis_client.close()

    async def ping(self) -> bool:
        return await self.redis_client.ping()

    async def cache_user(self, /, user: User):
        await self._cache_mapping(
            self._key_manager.user_id(user.id),
            {
                "first_name": user.first_name,
                "last_name": user.last_name or "",
                "email_address": user.email_address,
                "country_code": user.country_code,
                "country": user.country,
                "phone_number": user.phone_number or "",
            },
        )

        await self.redis_client.set(self._key_manager.user_email_address(user.email_address), user.id)

        if user.medical_data is not None:
            await self._cache_user_medical_data(user)

        if user.plan is not None:
            await self._cache_user_plan(user)

        if user.exercises:
            await self._cache_user_exercises(user)

    async def _cache_user_plan(self, /, user: User):
        plan = user.plan
        if plan is None or plan.is_empty():
            return

        maybe_awaitable = self.redis_client.json().set(self._key_manager.user_plan(user.id), "$", plan.model_dump())
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def _cache_user_exercises(self, /, user: User):
        exercises = user.exercises
        if not exercises:
            return

        maybe_awaitable = self.redis_client.json().set(
            self._key_manager.user_exercises(user.id), "$", [exercise.model_dump() for exercise in exercises]
        )
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def _cache_mapping(self, /, key: str, mapping: dict, *, expire: int | None = None):
        if mapping:
            maybe_awaitable = self.redis_client.hset(key, mapping=mapping)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

            if expire is not None:
                maybe_awaitable = self.redis_client.expire(key, expire)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

    async def _cache_user_medical_data(self, user: User):
        medical = user.medical_data

        if medical is None:
            return

        await self._cache_mapping(
            self._key_manager.user_medical_data(user.id),
            {
                "date_of_birth": medical.date_of_birth.isoformat(),
                "height": medical.height,
                "current_weight": medical.current_weight,
                "pre_pregnancy_weight": medical.pre_pregnancy_weight,
                "due_date": medical.due_date.isoformat(),
            },
        )

        medical_list_fields = {
            RedisKeyManager.MedicalField.DIETARY_PREFERENCES: medical.dietary_preferences,
            RedisKeyManager.MedicalField.FOOD_INTOLERANCES: medical.food_intolerances,
            RedisKeyManager.MedicalField.PRE_EXISTING_CONDITIONS: medical.pre_existing_conditions,
        }

        for field, values in medical_list_fields.items():
            if values:
                maybe_awaitable = self.redis_client.sadd(self._key_manager.user_medical_data_field(user.id, field), *values)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

    async def delete_user_cache(self, /, user_id: str, *, email_address: str | None = None):
        user_key = self._key_manager.user_id(user_id)
        medical_data_key = self._key_manager.user_medical_data(user_id)

        fields = [field for field in RedisKeyManager.MedicalField]
        medical_field_keys = [self._key_manager.user_medical_data_field(user_id, field) for field in fields]

        keys_to_delete = [user_key, medical_data_key] + medical_field_keys

        if email_address is not None:
            email_key = self._key_manager.user_email_address(email_address)
            keys_to_delete.append(email_key)

        maybe_awaitable = self.redis_client.delete(*keys_to_delete)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def get_user_id_by_email(self, /, email_address: str) -> str | None:
        return await self.redis_client.get(self._key_manager.user_email_address(email_address))

    async def get_user_by_id(self, /, user_id: str) -> User | None:
        from src.models import User, UserMedical

        user_data = self.redis_client.hgetall(self._key_manager.user_id(user_id))
        if inspect.isawaitable(user_data):
            user_data = await user_data

        if user_data is None:
            return None

        medical_data = self.redis_client.hgetall(self._key_manager.user_medical_data(user_id))
        if inspect.isawaitable(medical_data):
            medical_data = await medical_data

        if medical_data:
            fields: dict[str, set[str]] = {}
            for field in RedisKeyManager.MedicalField:
                values = self.redis_client.smembers(self._key_manager.user_medical_data_field(user_id, field))
                if inspect.isawaitable(values):
                    values = await values
                fields[field.value] = values

            medical_data.update(
                {
                    "dietary_preferences": list(fields[RedisKeyManager.MedicalField.DIETARY_PREFERENCES]),
                    "food_intolerances": list(fields[RedisKeyManager.MedicalField.FOOD_INTOLERANCES]),
                    "pre_existing_conditions": list(fields[RedisKeyManager.MedicalField.PRE_EXISTING_CONDITIONS]),
                }
            )

            user_data["medical_data"] = UserMedical.model_validate(medical_data)

        plan = self.redis_client.json().get(self._key_manager.user_plan(user_id))
        if inspect.isawaitable(plan):
            plan = await plan

        if plan is not None:
            user_data["plan"] = plan

        return User.model_validate(user_data)

    async def get_user_by_email(self, /, email_address: str) -> User | None:
        user_id = await self.get_user_id_by_email(email_address)
        if user_id is None:
            return None

        return await self.get_user_by_id(user_id)

    # Updating
    async def update_basics(self, /, user_id: str, field: UserField, value) -> bool:
        maybe_awaitable = self.redis_client.hset(self._key_manager.user_id(user_id), mapping={field: value})
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
        return True

    async def update_medical_data(self, /, user_id: str, field: UserField, value) -> bool:
        true_field = field.split(".")[-1]

        if field in {"date_of_birth", "due_date"} and hasattr(value, "isoformat"):
            value = value.isoformat()

        maybe_awaitable = self.redis_client.hset(self._key_manager.user_medical_data(user_id), mapping={field: value})
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
        return True

    async def cache_song_metadata(self, /, key: str, *, data: SongMetadataDict):
        await self._cache_mapping(self._key_manager.song_metadata(key), mapping={**data})

    async def get_song_metadata(self, /, key: str) -> SongMetadata:
        from src.models import SongMetadata

        maybe_data = self.redis_client.hgetall(self._key_manager.song_metadata(key))
        if inspect.isawaitable(maybe_data):
            maybe_data = await maybe_data

        return SongMetadata.model_validate(maybe_data)

    async def get_key_expiry(self, /, key: str):
        ttl = await self.redis_client.ttl(key)
        if ttl is not None:
            return datetime.now(timezone("UTC")) + timedelta(seconds=ttl)

        return None

    async def get_food_image(self, *, food_name: str) -> str | None:
        image = await self.redis_client.get(self._key_manager.food_image(food_name))
        if image is not None:
            return image

        return None
