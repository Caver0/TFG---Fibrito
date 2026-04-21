"""Routes for lightweight food catalog inspection and controlled enrichment."""
from fastapi import APIRouter, Depends, Query

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.food import FoodCatalogStatusResponse, FoodSearchResponse, serialize_food_catalog_item
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_status, search_food_sources

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search", response_model=FoodSearchResponse)
def search_foods(
    q: str = Query(min_length=2, max_length=80),
    include_external: bool = False,
    limit: int = Query(default=8, ge=1, le=10),
    _: UserPublic = Depends(get_current_user),
) -> FoodSearchResponse:
    database = get_database()
    foods, meta = search_food_sources(
        database,
        q,
        limit=limit,
        include_external=include_external,
    )
    return FoodSearchResponse(
        foods=[serialize_food_catalog_item(food) for food in foods],
        meta=meta,
    )


@router.get("/catalog/status", response_model=FoodCatalogStatusResponse)
def read_food_catalog_status(
    _: UserPublic = Depends(get_current_user),
) -> FoodCatalogStatusResponse:
    database = get_database()
    return FoodCatalogStatusResponse(**get_food_catalog_status(database))
