"""Routes for generating and retrieving user food-based diets."""
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.diet import (
    BuscarAlimentoSustitutoRequest,
    BuscarAlimentoSustitutoResponse,
    DailyDiet,
    DietGenerateRequest,
    DietListResponse,
    ManualDietCreateRequest,
    DietMutationResponse,
    FoodReplacementOptionsResponse,
    ReplaceFoodRequest,
)
from app.schemas.user import UserPublic
from app.services.diet_service import (
    activate_user_diet,
    generate_food_based_diet,
    get_active_user_diet,
    get_user_diet_by_id,
    list_user_diets,
    save_diet,
)
from app.services.food_substitution_service import (
    list_food_replacement_options,
    replace_food_in_meal,
    search_replacement_food,
)
from app.services.manual_diet_service import build_manual_diet_payload
from app.services.food_preferences_service import FoodPreferenceConflictError
from app.services.diet_runtime_audit import emit_runtime_audit, new_audit_id, runtime_audit_context
from app.services.diet_v2.telemetry import get_last_generation_diagnostics, get_last_regeneration_diagnostics
from app.services.meal_regeneration_service import regenerate_meal
from app.services.nutrition_service import NutritionProfileIncompleteError

router = APIRouter(prefix="/diets", tags=["diets"])


def _ensure_diet_supports_automatic_actions(database, user_id: str, diet_id: str) -> None:
    diet = get_user_diet_by_id(database, user_id, diet_id)
    if diet.diet_mode == "manual":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Manual diets do not support automatic regeneration or replacement actions",
        )


@router.post("/generate", response_model=DailyDiet, status_code=status.HTTP_201_CREATED)
def create_daily_diet(
    payload: DietGenerateRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()
    audit_id = new_audit_id("diet_generate")
    endpoint_started_at = time.perf_counter()

    with runtime_audit_context(audit_id=audit_id, endpoint="/diets/generate", user_id=current_user.id):
        emit_runtime_audit(
            "diet_generate_request_started",
            {
                "request_payload": payload.model_dump(mode="json"),
            },
        )
        try:
            diet_payload = generate_food_based_diet(
                database,
                current_user,
                payload.meals_count,
                custom_percentages=payload.custom_percentages,
                training_time_of_day=payload.training_time_of_day,
            )
            generation_diagnostics = get_last_generation_diagnostics() or {}
            persisted_diet = save_diet(database, current_user.id, diet_payload)
        except NutritionProfileIncompleteError as exc:
            emit_runtime_audit(
                "diet_generate_request_failed",
                {
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                    "generation_diagnostics": get_last_generation_diagnostics(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except FoodPreferenceConflictError as exc:
            emit_runtime_audit(
                "diet_generate_request_failed",
                {
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                    "generation_diagnostics": get_last_generation_diagnostics(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            emit_runtime_audit(
                "diet_generate_request_failed",
                {
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                    "generation_diagnostics": get_last_generation_diagnostics(),
                },
            )
            raise

        emit_runtime_audit(
            "diet_generate_request_completed",
            {
                "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                "generation_diagnostics": generation_diagnostics,
                "generated_payload_before_save": diet_payload,
                "persisted_payload": persisted_diet.model_dump(mode="json"),
                "returned_payload": persisted_diet.model_dump(mode="json"),
            },
        )
        return persisted_diet


@router.post("/manual", response_model=DailyDiet, status_code=status.HTTP_201_CREATED)
def create_manual_daily_diet(
    payload: ManualDietCreateRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()

    try:
        diet_payload = build_manual_diet_payload(
            database,
            current_user,
            payload,
        )
    except NutritionProfileIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return save_diet(
        database,
        current_user.id,
        diet_payload,
        adjusted_from_diet_id=payload.base_diet_id,
    )


@router.get("", response_model=DietListResponse)
def read_user_diet_history(
    current_user: UserPublic = Depends(get_current_user),
) -> DietListResponse:
    database = get_database()
    diets = list_user_diets(database, current_user.id)
    return DietListResponse(diets=diets)


@router.get("/latest", response_model=DailyDiet | None)
def read_latest_user_diet(
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet | None:
    database = get_database()
    return get_active_user_diet(database, current_user.id)


@router.get("/{diet_id}", response_model=DailyDiet)
def read_user_diet_by_id(
    diet_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()
    return get_user_diet_by_id(database, current_user.id, diet_id)


@router.post("/{diet_id}/activate", response_model=DailyDiet)
def activate_existing_user_diet(
    diet_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()
    return activate_user_diet(database, current_user.id, diet_id)


@router.post("/{diet_id}/meals/{meal_number}/regenerate", response_model=DietMutationResponse)
def regenerate_user_meal(
    diet_id: str,
    meal_number: int,
    current_user: UserPublic = Depends(get_current_user),
) -> DietMutationResponse:
    database = get_database()
    audit_id = new_audit_id("meal_regenerate")
    endpoint_started_at = time.perf_counter()
    _ensure_diet_supports_automatic_actions(database, current_user.id, diet_id)

    with runtime_audit_context(
        audit_id=audit_id,
        endpoint="/diets/{diet_id}/meals/{meal_number}/regenerate",
        user_id=current_user.id,
    ):
        emit_runtime_audit(
            "meal_regenerate_request_started",
            {
                "diet_id": diet_id,
                "meal_number": meal_number,
            },
        )
        try:
            response = regenerate_meal(
                database,
                user=current_user,
                diet_id=diet_id,
                meal_number=meal_number,
            )
        except FoodPreferenceConflictError as exc:
            emit_runtime_audit(
                "meal_regenerate_request_failed",
                {
                    "diet_id": diet_id,
                    "meal_number": meal_number,
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                    "regeneration_diagnostics": get_last_regeneration_diagnostics(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            emit_runtime_audit(
                "meal_regenerate_request_failed",
                {
                    "diet_id": diet_id,
                    "meal_number": meal_number,
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                    "regeneration_diagnostics": get_last_regeneration_diagnostics(),
                },
            )
            raise

        emit_runtime_audit(
            "meal_regenerate_request_completed",
            {
                "diet_id": diet_id,
                "meal_number": meal_number,
                "elapsed_seconds": time.perf_counter() - endpoint_started_at,
                "regeneration_diagnostics": get_last_regeneration_diagnostics(),
                "returned_payload": response.model_dump(mode="json"),
            },
        )
        return response


@router.post("/{diet_id}/meals/{meal_number}/replace-food", response_model=DietMutationResponse)
def replace_user_food_in_meal(
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> DietMutationResponse:
    database = get_database()
    _ensure_diet_supports_automatic_actions(database, current_user.id, diet_id)

    try:
        return replace_food_in_meal(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{diet_id}/meals/{meal_number}/replacement-options", response_model=FoodReplacementOptionsResponse)
def list_user_food_replacement_options(
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> FoodReplacementOptionsResponse:
    database = get_database()
    _ensure_diet_supports_automatic_actions(database, current_user.id, diet_id)

    try:
        return list_food_replacement_options(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/{diet_id}/meals/{meal_number}/search-replacement-food",
    response_model=BuscarAlimentoSustitutoResponse,
)
def search_user_replacement_food(
    diet_id: str,
    meal_number: int,
    payload: BuscarAlimentoSustitutoRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> BuscarAlimentoSustitutoResponse:
    database = get_database()
    _ensure_diet_supports_automatic_actions(database, current_user.id, diet_id)

    try:
        return search_replacement_food(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
