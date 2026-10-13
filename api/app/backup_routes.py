"""GET /api/backups: the state of the off-box backup, for the web and its alert banner."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from . import backup_status
from .auth.deps import current_user

router = APIRouter(prefix="/api/backups", tags=["backups"], dependencies=[Depends(current_user)])


@router.get("")
def backups() -> dict:
    return backup_status.status()
