from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.app import app
from src.utils import Token

from ..utils import data_handler, get_user_token

router = APIRouter(prefix="/update", tags=["Update Management"])


@router.put("/first-name", summary="Update user's first name")
async def update_first_name(new_first_name: str, token: Token = Depends(get_user_token)):
    """
    Update the first name of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(email_address=user.email_address, set_fields={"first_name": new_first_name})
    await data_handler.cache_handler.update_first_name(user.email_address, new_first_name)
    return database_updated


@router.put("/last-name", summary="Update user's last name")
async def update_last_name(new_last_name: str, token: Token = Depends(get_user_token)):
    """
    Update the last name of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(email_address=user.email_address, set_fields={"last_name": new_last_name})
    await data_handler.cache_handler.update_last_name(user.email_address, new_last_name)
    return database_updated


@router.put("/medical-data/date-of-birth", summary="Update user's date of birth")
async def update_date_of_birth(new_date_of_birth: str, token: Token = Depends(get_user_token)):
    """
    Update the date of birth of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.date_of_birth": new_date_of_birth}
    )
    await data_handler.cache_handler.update_date_of_birth(user.email_address, new_date_of_birth)
    return database_updated


@router.put("/medical-data/height", summary="Update user's height")
async def update_height(new_height: float, token: Token = Depends(get_user_token)):
    """
    Update the height of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(email_address=user.email_address, set_fields={"medical_data.height": new_height})
    await data_handler.cache_handler.update_height(user.email_address, new_height)
    return database_updated


@router.put("/medical-data/current-weight", summary="Update user's current weight")
async def update_current_weight(new_current_weight: float, token: Token = Depends(get_user_token)):
    """
    Update the current weight of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.current_weight": new_current_weight}
    )
    await data_handler.cache_handler.update_current_weight(user.email_address, new_current_weight)
    return database_updated


@router.put("/medical-data/pre-pregnancy-weight", summary="Update user's pre-pregnancy weight")
async def update_pre_pregnancy_weight(new_pre_pregnancy_weight: float, token: Token = Depends(get_user_token)):
    """
    Update the pre-pregnancy weight of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.pre_pregnancy_weight": new_pre_pregnancy_weight}
    )
    await data_handler.cache_handler.update_pre_pregnancy_weight(user.email_address, new_pre_pregnancy_weight)
    return database_updated


@router.put("/medical-data/due-date", summary="Update user's due date")
async def update_due_date(new_due_date: str, token: Token = Depends(get_user_token)):
    """
    Update the due date of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.due_date": new_due_date}
    )
    await data_handler.cache_handler.update_due_date(user.email_address, new_due_date)
    return database_updated


@router.put("/medical-data/pre-existing-conditions/add", summary="Add a pre-existing condition to user's medical data")
async def add_pre_existing_condition(condition: str, token: Token = Depends(get_user_token)):
    """
    Add a pre-existing condition to the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, add_to_set={"medical_data.pre_existing_conditions": condition}
    )
    await data_handler.cache_handler.add_pre_existing_condition(user.email_address, condition)

    return database_updated


@router.put("/medical-data/pre-existing-conditions/remove", summary="Remove a pre-existing condition from user's medical data")
async def remove_pre_existing_condition(condition: str, token: Token = Depends(get_user_token)):
    """
    Remove a pre-existing condition from the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, pull_from_set={"medical_data.pre_existing_conditions": condition}
    )
    await data_handler.cache_handler.remove_pre_existing_condition(user.email_address, condition)

    return database_updated


@router.put("/medical-data/pre-existing-conditions", summary="Set user's pre-existing conditions")
async def set_pre_existing_conditions(conditions: list[str], token: Token = Depends(get_user_token)):
    """
    Set the pre-existing conditions of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.pre_existing_conditions": conditions}
    )
    await data_handler.cache_handler.set_pre_existing_conditions(user.email_address, conditions)
    return database_updated


@router.put("/medical-data/food-intolerances/add", summary="Add a food intolerance to user's medical data")
async def add_food_intolerance(condition: str, token: Token = Depends(get_user_token)):
    """
    Add a food intolerance to the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, add_to_set={"medical_data.food_intolerances": condition}
    )
    await data_handler.cache_handler.add_food_intolerance(user.email_address, condition)

    return database_updated


@router.put("/medical-data/food-intolerances/remove", summary="Remove a food intolerance from user's medical data")
async def remove_food_intolerance(condition: str, token: Token = Depends(get_user_token)):
    """
    Remove a food intolerance from the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, pull_from_set={"medical_data.food_intolerances": condition}
    )
    await data_handler.cache_handler.remove_food_intolerance(user.email_address, condition)

    return database_updated


@router.put("/medical-data/food-intolerances", summary="Set user's food intolerances")
async def set_food_intolerances(conditions: list[str], token: Token = Depends(get_user_token)):
    """
    Set the food intolerances of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.food_intolerances": conditions}
    )
    await data_handler.cache_handler.set_food_intolerances(user.email_address, conditions)
    return database_updated


@router.put("/medical-data/dietary-preferences/add", summary="Add a dietary preference to user's medical data")
async def add_dietary_preference(preference: str, token: Token = Depends(get_user_token)):
    """
    Add a dietary preference to the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, add_to_set={"medical_data.dietary_preferences": preference}
    )
    await data_handler.cache_handler.add_dietary_preference(user.email_address, preference)

    return database_updated


@router.put("/medical-data/dietary-preferences/remove", summary="Remove a dietary preference from user's medical data")
async def remove_dietary_preference(preference: str, token: Token = Depends(get_user_token)):
    """
    Remove a dietary preference from the authenticated user's medical data.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, pull_from_set={"medical_data.dietary_preferences": preference}
    )
    await data_handler.cache_handler.remove_dietary_preference(user.email_address, preference)

    return database_updated


@router.put("/medical-data/dietary-preferences", summary="Set user's dietary preferences")
async def set_dietary_preferences(preferences: list[str], token: Token = Depends(get_user_token)):
    """
    Set the dietary preferences of the authenticated user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    database_updated = await data_handler.update_user(
        email_address=user.email_address, set_fields={"medical_data.dietary_preferences": preferences}
    )
    await data_handler.cache_handler.set_dietary_preferences(user.email_address, preferences)
    return database_updated
