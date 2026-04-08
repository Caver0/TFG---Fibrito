"""Routes for authenticated weight tracking."""
from fastapi import APIRouter, Depends, Response, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.progress import ProgressSummary
from app.schemas.user import UserPublic
from app.schemas.weight import WeightEntry, WeightEntryCreate, WeightEntryList
from app.services.progress_service import (
    build_progress_summary,
    create_weight_entry,
    delete_weight_entry,
    list_weight_entries,
)

router = APIRouter(prefix="/weight", tags=["weight"])


@router.post("", response_model=WeightEntry, status_code=status.HTTP_201_CREATED)
def create_current_user_weight_entry(
    payload: WeightEntryCreate,
    current_user: UserPublic = Depends(get_current_user),
) -> WeightEntry:
    database = get_database()
    return create_weight_entry(database, current_user.id, payload)


@router.get("", response_model=WeightEntryList)
def read_current_user_weight_history(
    current_user: UserPublic = Depends(get_current_user),
) -> WeightEntryList:
    database = get_database()
    entries = list_weight_entries(database, current_user.id)
    return WeightEntryList(entries=entries)


@router.get("/summary", response_model=ProgressSummary)
def read_current_user_progress_summary(
    current_user: UserPublic = Depends(get_current_user),
) -> ProgressSummary:
    database = get_database()
    entries = list_weight_entries(database, current_user.id)
    return build_progress_summary(entries)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user_weight_entry(
    entry_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> Response:
    database = get_database()
    delete_weight_entry(database, current_user.id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
