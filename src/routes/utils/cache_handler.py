from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pytz import timezone
from redis.asyncio import Redis

from .redis_key_manager import RedisKeyManager

if TYPE_CHECKING:
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

    async def _resolve_user_id(self, email_address: str) -> str | None:
        return await self.get_user_id_by_email(email_address)

    async def _maybe_await(self, obj: Any):
        if inspect.isawaitable(obj):
            await obj

    async def _update_hash_field(self, email_address: str, key_func, field: str, value: Any):
        user_id = await self._resolve_user_id(email_address)
        if not user_id:
            return
        await self._maybe_await(self.redis_client.hset(key_func(user_id), mapping={field: value}))

    async def _update_set_field(self, email_address: str, key_func, action: str, value: Any):
        user_id = await self._resolve_user_id(email_address)
        if not user_id:
            return
        func = getattr(self.redis_client, action)
        await self._maybe_await(func(key_func(user_id), value))

    async def _reset_set_field(self, email_address: str, key_func, values: list[str]):
        user_id = await self._resolve_user_id(email_address)
        if not user_id:
            return
        key = key_func(user_id)
        await self._maybe_await(self.redis_client.delete(key))
        if values:
            await self._maybe_await(self.redis_client.sadd(key, *values))

    # --- public methods ---

    async def update_first_name(self, email_address: str, value: str):
        await self._update_hash_field(email_address, self._key_manager.user_id, "first_name", value)

    async def update_last_name(self, email_address: str, value: str):
        await self._update_hash_field(email_address, self._key_manager.user_id, "last_name", value)

    async def update_date_of_birth(self, email_address: str, value: str):
        await self._update_hash_field(email_address, self._key_manager.user_medical_data, "date_of_birth", value)

    async def update_height(self, email_address: str, value: float):
        await self._update_hash_field(email_address, self._key_manager.user_medical_data, "height", value)

    async def update_current_weight(self, email_address: str, value: float):
        await self._update_hash_field(email_address, self._key_manager.user_medical_data, "current_weight", value)

    async def update_pre_pregnancy_weight(self, email_address: str, value: float):
        await self._update_hash_field(email_address, self._key_manager.user_medical_data, "pre_pregnancy_weight", value)

    async def update_due_date(self, email_address: str, value: str):
        await self._update_hash_field(email_address, self._key_manager.user_medical_data, "due_date", value)

    async def add_pre_existing_condition(self, email_address: str, condition: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.PRE_EXISTING_CONDITIONS),
            "sadd",
            condition,
        )

    async def remove_pre_existing_condition(self, email_address: str, condition: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.PRE_EXISTING_CONDITIONS),
            "srem",
            condition,
        )

    async def set_pre_existing_conditions(self, email_address: str, conditions: list[str]):
        await self._reset_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.PRE_EXISTING_CONDITIONS),
            conditions,
        )

    async def add_food_intolerance(self, email_address: str, condition: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.FOOD_INTOLERANCES),
            "sadd",
            condition,
        )

    async def remove_food_intolerance(self, email_address: str, condition: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.FOOD_INTOLERANCES),
            "srem",
            condition,
        )

    async def set_food_intolerances(self, email_address: str, conditions: list[str]):
        await self._reset_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.FOOD_INTOLERANCES),
            conditions,
        )

    async def add_dietary_preference(self, email_address: str, prefrence: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.DIETARY_PREFERENCES),
            "sadd",
            prefrence,
        )

    async def remove_dietary_preference(self, email_address: str, prefrence: str):
        await self._update_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.DIETARY_PREFERENCES),
            "srem",
            prefrence,
        )

    async def set_dietary_preferences(self, email_address: str, preferences: list[str]):
        await self._reset_set_field(
            email_address,
            lambda uid: self._key_manager.user_medical_data_field(uid, self._key_manager.MedicalField.DIETARY_PREFERENCES),
            preferences,
        )
