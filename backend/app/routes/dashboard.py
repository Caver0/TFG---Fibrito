"""Routes for the aggregated dashboard overview."""
from fastapi import APIRouter, Depends

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.dashboard import DashboardOverviewResponse
from app.schemas.user import UserPublic
from app.services.dashboard_service import build_dashboard_overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def read_dashboard_overview(
    current_user: UserPublic = Depends(get_current_user),
) -> DashboardOverviewResponse:
    database = get_database()
    return build_dashboard_overview(database, current_user)
