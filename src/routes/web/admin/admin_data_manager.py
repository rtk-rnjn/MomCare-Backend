from __future__ import annotations

import uuid
from typing import Any

import arrow
import orjson
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import AccountStatus, CredentialsDict, UserDict

router = APIRouter()

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates
email_normalizer = app.state.email_normalizer
google_api_handler = app.state.google_api_handler


ALLOWED_COLLECTIONS = {
    "users",
    "credentials",
    "foods",
    "songs",
    "exercises",
    "plans",
    "tips",
    "user_exercises",
}


COLLECTION_FIELD_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "users": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "first_name", "type": "string"},
        {"name": "last_name", "type": "string"},
        {"name": "phone_number", "type": "string"},
        {"name": "date_of_birth_timestamp", "type": "number"},
        {"name": "height", "type": "number"},
        {"name": "pre_pregnancy_weight", "type": "number"},
        {"name": "current_weight", "type": "number"},
        {"name": "due_date_timestamp", "type": "number"},
        {"name": "food_intolerances", "type": "json"},
        {"name": "dietary_preferences", "type": "json"},
        {"name": "timezone", "type": "string"},
    ],
    "credentials": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "email_address", "type": "string"},
        {"name": "email_address_normalized", "type": "string"},
        {"name": "email_address_provider", "type": "string"},
        {"name": "authentication_providers", "type": "json"},
        {"name": "verified_email", "type": "boolean"},
        {"name": "account_status", "type": "enum", "options": ["active", "locked", "deleted"]},
        {"name": "failed_login_attempts", "type": "number"},
        {"name": "locked_until_timestamp", "type": "number"},
    ],
    "foods": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "name", "type": "string"},
        {"name": "state", "type": "string"},
        {"name": "type", "type": "string"},
        {"name": "allergic_ingredients", "type": "json"},
        {"name": "vitamin_content", "type": "json"},
        {"name": "total_calories", "type": "number"},
        {"name": "total_carbs_in_g", "type": "number"},
        {"name": "total_fats_in_g", "type": "number"},
        {"name": "total_protein_in_g", "type": "number"},
        {"name": "total_sugar_in_g", "type": "number"},
        {"name": "total_sodium_in_mg", "type": "number"},
        {"name": "image_uri", "type": "string"},
    ],
    "songs": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "song_name", "type": "string"},
        {"name": "mood", "type": "string"},
        {"name": "playlist", "type": "string"},
        {"name": "metadata", "type": "json"},
    ],
    "exercises": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "name", "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "level", "type": "string"},
        {"name": "week", "type": "string"},
        {"name": "tags", "type": "json"},
        {"name": "benefits", "type": "json"},
        {"name": "contraindications", "type": "json"},
    ],
    "plans": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "user_id", "type": "string"},
        {"name": "breakfast", "type": "json"},
        {"name": "lunch", "type": "json"},
        {"name": "dinner", "type": "json"},
        {"name": "snacks", "type": "json"},
        {"name": "created_at_timestamp", "type": "number"},
    ],
    "tips": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "user_id", "type": "string"},
        {"name": "todays_focus", "type": "string"},
        {"name": "daily_tip", "type": "string"},
        {"name": "created_at_timestamp", "type": "number"},
    ],
    "user_exercises": [
        {"name": "_id", "type": "string", "readonly": True, "required": False},
        {"name": "user_id", "type": "string"},
        {"name": "exercise_id", "type": "string"},
        {"name": "completed", "type": "boolean"},
        {"name": "added_at_timestamp", "type": "number"},
        {"name": "completed_at_timestamp", "type": "number"},
    ],
}


COLLECTION_SHORTCUTS: dict[str, list[dict[str, str]]] = {
    "credentials": [
        {"action": "lock", "label": "Lock Account"},
        {"action": "unlock", "label": "Unlock Account"},
        {"action": "change_email", "label": "Change Email"},
        {"action": "verify_email", "label": "Verify Email"},
        {"action": "unverify_email", "label": "Unverify Email"},
        {"action": "reset_login_attempts", "label": "Reset Login Attempts"},
        {"action": "regen_plan", "label": "Regenerate Plan"},
        {"action": "delete_today_plan", "label": "Delete Today's Plan"},
    ],
    "plans": [
        {"action": "regen_plan", "label": "Regenerate Plan (by user_id)"},
        {"action": "delete_today_plan", "label": "Delete Today's Plan (by user_id)"},
    ],
}


def _ensure_collection_allowed(collection_name: str) -> str:
    if collection_name not in ALLOWED_COLLECTIONS:
        raise HTTPException(status_code=400, detail="Collection not allowed")
    return collection_name


def _id_filter(doc_id: str) -> dict[str, Any]:
    return {"_id": doc_id}


def _validate_uuid(value: Any, field_name: str = "_id") -> str:
    try:
        parsed = uuid.UUID(str(value))
        return str(parsed)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid UUID for {field_name}")


def _validate_document_ids(document: dict[str, Any]) -> dict[str, Any]:
    validated = dict(document)

    if "_id" in validated and validated["_id"] not in (None, ""):
        validated["_id"] = _validate_uuid(validated["_id"], "_id")
    else:
        validated["_id"] = str(uuid.uuid4())

    if "user_id" in validated and validated["user_id"] not in (None, ""):
        validated["user_id"] = _validate_uuid(validated["user_id"], "user_id")

    if "exercise_id" in validated and validated["exercise_id"] not in (None, ""):
        validated["exercise_id"] = _validate_uuid(validated["exercise_id"], "exercise_id")

    return validated


def _to_jsonable(value: Any) -> Any:
    return orjson.loads(orjson.dumps(value, default=str))


async def _build_plan_for_user(user_id: str) -> dict[str, Any]:
    user_id = _validate_uuid(user_id, "user_id")
    users_collection = database["users"]
    foods_collection = database["foods"]
    plans_collection = database["plans"]

    user: UserDict | None = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    timezone = user.get("timezone") or "Asia/Kolkata"
    now = arrow.now(timezone)
    start = now.floor("day").float_timestamp
    end = now.ceil("day").float_timestamp

    await plans_collection.delete_many(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": start,
                "$lte": end,
            },
        }
    )

    food_intolerances = user.get("food_intolerances", [])
    dietary_preferences = user.get("dietary_preferences", [])

    pipeline: list[dict[str, Any]] = []
    if food_intolerances:
        pipeline.append({"$match": {"allergic_ingredients": {"$not": {"$elemMatch": {"$in": food_intolerances}}}}})
    if dietary_preferences:
        pipeline.append({"$match": {"type": {"$in": dietary_preferences}}})

    foods_cursor = await foods_collection.aggregate(pipeline)
    foods = [{"_id": food.get("_id"), "name": food.get("name")} async for food in foods_cursor]

    plan = await google_api_handler.generate_plan(user=user, available_foods=foods)
    plan.created_at_timestamp = arrow.now().float_timestamp
    plan.user_id = user_id
    plan.id = str(uuid.uuid4())

    plan_dict = plan.model_dump(by_alias=True, mode="json")
    await plans_collection.insert_one(plan_dict)
    return plan_dict


async def _delete_today_plan_for_user(user_id: str) -> int:
    user_id = _validate_uuid(user_id, "user_id")
    users_collection = database["users"]
    plans_collection = database["plans"]

    user: UserDict | None = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    timezone = user.get("timezone") or "Asia/Kolkata"
    now = arrow.now(timezone)
    start = now.floor("day").float_timestamp
    end = now.ceil("day").float_timestamp

    result = await plans_collection.delete_many(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": start,
                "$lte": end,
            },
        }
    )
    return result.deleted_count


@router.get("/data-manager", include_in_schema=False)
async def admin_data_manager(request: Request):
    return templates.TemplateResponse("data_manager.html.jinja", {"request": request})


@router.get("/data-manager/api/collections", include_in_schema=False)
async def admin_data_manager_collections():
    names = sorted([name for name in await database.list_collection_names() if name in ALLOWED_COLLECTIONS])
    return JSONResponse({"collections": names})


@router.get("/data-manager/api/schema/{collection_name}", include_in_schema=False)
async def admin_data_manager_collection_schema(collection_name: str):
    name = _ensure_collection_allowed(collection_name)
    return JSONResponse(
        {
            "collection": name,
            "fields": COLLECTION_FIELD_SCHEMAS.get(name, []),
            "shortcuts": COLLECTION_SHORTCUTS.get(name, []),
        }
    )


@router.get("/data-manager/api/{collection_name}", include_in_schema=False)
async def admin_data_manager_list_collection(
    collection_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    name = _ensure_collection_allowed(collection_name)
    collection = database[name]

    total = await collection.count_documents({})
    cursor = collection.find({}).sort("_id", 1).skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(length=page_size)

    return JSONResponse(
        {
            "items": _to_jsonable(docs),
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    )


@router.post("/data-manager/api/{collection_name}", include_in_schema=False)
async def admin_data_manager_create_document(
    collection_name: str,
    payload: dict[str, Any] = Body(...),
):
    name = _ensure_collection_allowed(collection_name)
    collection = database[name]

    document = payload.get("document")
    if not isinstance(document, dict):
        raise HTTPException(status_code=400, detail="Invalid document payload")

    document = _validate_document_ids(document)

    await collection.insert_one(document)
    return JSONResponse({"ok": True})


@router.put("/data-manager/api/{collection_name}/{doc_id}", include_in_schema=False)
async def admin_data_manager_update_document(
    collection_name: str,
    doc_id: str,
    payload: dict[str, Any] = Body(...),
):
    name = _ensure_collection_allowed(collection_name)
    doc_id = _validate_uuid(doc_id, "doc_id")
    collection = database[name]

    updates = payload.get("updates")
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="Invalid updates payload")

    updates.pop("_id", None)
    if "user_id" in updates and updates["user_id"] not in (None, ""):
        updates["user_id"] = _validate_uuid(updates["user_id"], "user_id")
    if "exercise_id" in updates and updates["exercise_id"] not in (None, ""):
        updates["exercise_id"] = _validate_uuid(updates["exercise_id"], "exercise_id")

    result = await collection.update_one(_id_filter(doc_id), {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    return JSONResponse({"ok": True})


@router.delete("/data-manager/api/{collection_name}/{doc_id}", include_in_schema=False)
async def admin_data_manager_delete_document(collection_name: str, doc_id: str):
    name = _ensure_collection_allowed(collection_name)
    doc_id = _validate_uuid(doc_id, "doc_id")
    collection = database[name]

    result = await collection.delete_one(_id_filter(doc_id))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    return JSONResponse({"ok": True})


@router.post("/data-manager/api/users/{user_id}/lock", include_in_schema=False)
async def admin_data_manager_lock_user(
    user_id: str,
    payload: dict[str, Any] = Body(...),
):
    user_id = _validate_uuid(user_id, "user_id")
    credentials_collection = database["credentials"]

    lock = bool(payload.get("lock", True))
    account_status = AccountStatus.LOCKED if lock else AccountStatus.ACTIVE

    result = await credentials_collection.update_one({"_id": user_id}, {"$set": {"account_status": account_status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User credentials not found")

    return JSONResponse({"ok": True, "account_status": account_status})


@router.post("/data-manager/api/credentials/{credential_id}/lock", include_in_schema=False)
async def admin_data_manager_lock_credential(
    credential_id: str,
    payload: dict[str, Any] = Body(...),
):
    credential_id = _validate_uuid(credential_id, "credential_id")
    return await admin_data_manager_lock_user(user_id=credential_id, payload=payload)


@router.post("/data-manager/api/users/{user_id}/email", include_in_schema=False)
async def admin_data_manager_change_email(
    user_id: str,
    payload: dict[str, Any] = Body(...),
):
    user_id = _validate_uuid(user_id, "user_id")
    credentials_collection = database["credentials"]

    email_address = str(payload.get("email", "")).strip()
    if not email_address:
        raise HTTPException(status_code=400, detail="Email is required")

    normalization_result = await email_normalizer.normalize(email_address)

    duplicate = await credentials_collection.find_one(
        {
            "$or": [
                {"email_address": email_address},
                {"email_address_normalized": normalization_result.cleaned_email},
            ],
            "_id": {"$ne": user_id},
        }
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Email already used by another account")

    now_ts = arrow.utcnow().float_timestamp
    result = await credentials_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "email_address": email_address,
                "email_address_normalized": normalization_result.cleaned_email,
                "email_address_provider": normalization_result.mailbox_provider,
                "updated_at_timestamp": now_ts,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User credentials not found")

    return JSONResponse(
        {
            "ok": True,
            "email_address": email_address,
            "email_address_normalized": normalization_result.cleaned_email,
        }
    )


@router.post("/data-manager/api/credentials/{credential_id}/email", include_in_schema=False)
async def admin_data_manager_change_credential_email(
    credential_id: str,
    payload: dict[str, Any] = Body(...),
):
    credential_id = _validate_uuid(credential_id, "credential_id")
    return await admin_data_manager_change_email(user_id=credential_id, payload=payload)


@router.post("/data-manager/api/credentials/{credential_id}/verify-email", include_in_schema=False)
async def admin_data_manager_verify_email(
    credential_id: str,
    payload: dict[str, Any] = Body(...),
):
    credential_id = _validate_uuid(credential_id, "credential_id")
    credentials_collection = database["credentials"]

    verified = bool(payload.get("verified", True))
    now_ts = arrow.utcnow().float_timestamp

    result = await credentials_collection.update_one(
        {"_id": credential_id},
        {
            "$set": {
                "verified_email": verified,
                "verified_email_at_timestamp": now_ts if verified else None,
                "updated_at_timestamp": now_ts,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Credentials not found")

    return JSONResponse({"ok": True, "verified_email": verified})


@router.post("/data-manager/api/credentials/{credential_id}/reset-login-attempts", include_in_schema=False)
async def admin_data_manager_reset_login_attempts(credential_id: str):
    credential_id = _validate_uuid(credential_id, "credential_id")
    credentials_collection = database["credentials"]
    now_ts = arrow.utcnow().float_timestamp

    result = await credentials_collection.update_one(
        {"_id": credential_id},
        {
            "$set": {
                "failed_login_attempts": 0,
                "failed_login_attempts_timestamp": None,
                "locked_until_timestamp": None,
                "account_status": AccountStatus.ACTIVE,
                "updated_at_timestamp": now_ts,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Credentials not found")

    return JSONResponse({"ok": True})


@router.post("/data-manager/api/users/{user_id}/regen-plan", include_in_schema=False)
async def admin_data_manager_regen_plan(user_id: str):
    user_id = _validate_uuid(user_id, "user_id")
    credentials_collection = database["credentials"]

    cred: CredentialsDict | None = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(status_code=404, detail="User credentials not found")

    if cred.get("account_status") == AccountStatus.LOCKED:
        raise HTTPException(status_code=423, detail="User is locked")

    plan = await _build_plan_for_user(user_id)
    return JSONResponse({"ok": True, "plan": _to_jsonable(plan)})


@router.post("/data-manager/api/credentials/{credential_id}/regen-plan", include_in_schema=False)
async def admin_data_manager_regen_plan_by_credential(credential_id: str):
    credential_id = _validate_uuid(credential_id, "credential_id")
    return await admin_data_manager_regen_plan(user_id=credential_id)


@router.post("/data-manager/api/users/{user_id}/delete-today-plan", include_in_schema=False)
async def admin_data_manager_delete_today_plan(user_id: str):
    user_id = _validate_uuid(user_id, "user_id")
    credentials_collection = database["credentials"]
    cred: CredentialsDict | None = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(status_code=404, detail="User credentials not found")

    deleted_count = await _delete_today_plan_for_user(user_id)
    return JSONResponse({"ok": True, "deleted_count": deleted_count})


@router.post("/data-manager/api/credentials/{credential_id}/delete-today-plan", include_in_schema=False)
async def admin_data_manager_delete_today_plan_by_credential(credential_id: str):
    credential_id = _validate_uuid(credential_id, "credential_id")
    return await admin_data_manager_delete_today_plan(user_id=credential_id)
