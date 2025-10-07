from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.app import app
from src.utils import Token

from .utils import data_handler, get_user_token

router = APIRouter(prefix="/update", tags=["Update Management"])


@router.put("/first-name", summary="Update user's first name")
async def update_first_name(request: Request, new_first_name: str, token: Token = Depends(get_user_token)):
    """
    Update the first name of the authenticated user.

    - **new_first_name**: The new first name to set for the user.
    - **token**: JWT token for authenticating the user.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    await data_handler.update_user(email_address=user.email_address, set_fields={"first_name": new_first_name})
    return {"success": True, "message": "First name updated successfully"}
