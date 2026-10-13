"""GET/PUT /api/settings/reminders: when the bot asks, and whether it does."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import reminders
from .auth.deps import current_user
from .health import quality

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(current_user)])


class ReminderPatch(BaseModel):
    enabled: bool | None = None
    time: str | None = None


class RemindersPatch(BaseModel):
    morning_feeling: ReminderPatch | None = None
    evening_checkin: ReminderPatch | None = None


def _payload(current: dict) -> dict:
    return {"timezone": str(quality.user_timezone()),
            "reminders": [{"key": k, "label": reminders.NAMES[k]["label"], **v} for k, v in current.items()]}


@router.get("/reminders")
def get_reminders() -> dict:
    return _payload(reminders.load())


@router.put("/reminders")
def put_reminders(body: RemindersPatch) -> dict:
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items() if v}
    if not changes:
        raise HTTPException(422, "Nothing to change.")
    try:
        return _payload(reminders.save(changes))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
