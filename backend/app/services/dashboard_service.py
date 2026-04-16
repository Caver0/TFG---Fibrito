"""Business logic for the aggregated user dashboard overview."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from app.schemas.dashboard import (
    ActiveDietMealOverview,
    ActiveDietOverview,
    AdherenceDailyBreakdownPoint,
    AdherenceOverview,
    CalorieAdjustmentEventPoint,
    DashboardMacroSummary,
    DashboardOverviewResponse,
    DashboardSummaryMetrics,
    ExpectedWeightTrendPoint,
    RegressionTrendPoint,
    WeightProgressOverview,
    WeightProgressPoint,
    WeeklyWeightAveragePoint,
)
from app.schemas.nutrition import NutritionSummary
from app.schemas.user import UserPublic
from app.services.adherence_service import (
    calculate_daily_adherence_summary,
    calculate_weekly_adherence_summary,
)
from app.services.diet_service import get_latest_user_diet
from app.services.goal_adjustment_service import (
    analyze_weekly_progress,
    list_adjustment_history,
)
from app.services.nutrition_service import NutritionProfileIncompleteError, build_nutrition_summary
from app.services.progress_service import (
    calculate_weekly_averages,
    get_week_bounds,
    list_weight_entries,
    round_progress_value,
)

DAY_LABELS = ("Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom")
MIN_WEEKLY_LOSS_REFERENCE = Decimal("0.30")
EXPECTED_WEEKLY_GAIN = Decimal("0.10")
EXPECTED_WEEKLY_MAINTENANCE = Decimal("0.00")
WEEK_LENGTH_DAYS = Decimal("7")


def _safe_round(value: float | Decimal | None) -> float | None:
    if value is None:
        return None

    return round_progress_value(float(value))


def _parse_week_label(week_label: str | None) -> tuple[int, int] | None:
    normalized_label = str(week_label or "").strip()
    if not normalized_label:
        return None

    try:
        iso_year_raw, iso_week_raw = normalized_label.split("-W", maxsplit=1)
        return int(iso_year_raw), int(iso_week_raw)
    except ValueError:
        return None


def _resolve_week_end_date(
    week_label: str | None,
    fallback_date: date | None = None,
) -> date:
    parsed_week = _parse_week_label(week_label)
    if parsed_week is None:
        return fallback_date or datetime.now(UTC).date()

    _, end_date = get_week_bounds(*parsed_week)
    return end_date


def _get_current_nutrition_summary(user: UserPublic) -> NutritionSummary | None:
    try:
        return build_nutrition_summary(
            user,
            target_calories_override=user.target_calories,
        )
    except NutritionProfileIncompleteError:
        return None


def get_weight_progress_series(entries) -> list[WeightProgressPoint]:
    return [
        WeightProgressPoint(
            date=entry.date,
            weight=_safe_round(entry.weight),
        )
        for entry in entries
    ]


def get_weekly_weight_averages(entries) -> list[WeeklyWeightAveragePoint]:
    return [
        WeeklyWeightAveragePoint(
            week_label=average.week_label,
            start_date=average.start_date,
            end_date=average.end_date,
            average_weight=_safe_round(average.average_weight),
            entry_count=average.entry_count,
            is_complete=average.is_complete,
        )
        for average in calculate_weekly_averages(entries)
    ]


def _build_expected_trend_dates(
    weight_progress_series: list[WeightProgressPoint],
    weekly_weight_averages: list[WeeklyWeightAveragePoint],
) -> list[date]:
    if not weight_progress_series:
        return []

    reference_dates = {
        point.date
        for point in weight_progress_series
    }
    reference_dates.update(
        average.end_date for average in weekly_weight_averages
    )
    reference_dates.add(weight_progress_series[0].date)
    reference_dates.add(weight_progress_series[-1].date)
    return sorted(reference_dates)


def _get_expected_weekly_change(goal: str | None, reference_weight: float | None) -> tuple[Decimal | None, str | None]:
    if goal == "ganar_masa":
        return (
            EXPECTED_WEEKLY_GAIN,
            "Referencia esperada segun objetivo de ganancia (+0.10 kg/semana).",
        )

    if goal == "mantener_peso":
        return (
            EXPECTED_WEEKLY_MAINTENANCE,
            "Referencia esperada segun objetivo de mantenimiento (estable).",
        )

    if goal == "perder_grasa" and reference_weight is not None:
        max_weekly_loss = Decimal(str(reference_weight)) * Decimal("0.01")
        reference_loss = (MIN_WEEKLY_LOSS_REFERENCE + max(max_weekly_loss, MIN_WEEKLY_LOSS_REFERENCE)) / Decimal("2")
        rounded_reference_loss = _safe_round(reference_loss) or 0.0
        return (
            -reference_loss,
            (
                "Referencia esperada segun objetivo de perdida "
                f"(aprox. -{rounded_reference_loss:.2f} kg/semana)."
            ),
        )

    return None, None


def get_expected_weight_trend(
    user: UserPublic,
    weight_progress_series: list[WeightProgressPoint],
    weekly_weight_averages: list[WeeklyWeightAveragePoint],
) -> tuple[list[ExpectedWeightTrendPoint], str | None]:
    if not weight_progress_series:
        return [], None

    baseline_point = weight_progress_series[0]
    expected_weekly_change, trend_label = _get_expected_weekly_change(
        user.goal,
        baseline_point.weight,
    )
    if expected_weekly_change is None:
        return [], None

    trend_dates = _build_expected_trend_dates(weight_progress_series, weekly_weight_averages)
    if len(trend_dates) < 2:
        return [], trend_label

    baseline_weight = Decimal(str(baseline_point.weight))
    expected_daily_change = expected_weekly_change / WEEK_LENGTH_DAYS
    trend_points: list[ExpectedWeightTrendPoint] = []

    for trend_date in trend_dates:
        elapsed_days = Decimal(str((trend_date - baseline_point.date).days))
        expected_weight = baseline_weight + (expected_daily_change * elapsed_days)
        trend_points.append(
            ExpectedWeightTrendPoint(
                date=trend_date,
                expected_weight=_safe_round(expected_weight),
            )
        )

    return trend_points, trend_label


def get_calorie_adjustment_events(database, user_id: str) -> list[CalorieAdjustmentEventPoint]:
    adjustment_history = list_adjustment_history(database, user_id)
    event_points: list[CalorieAdjustmentEventPoint] = []

    for adjustment in adjustment_history:
        if not adjustment.adjustment_applied or adjustment.calorie_change == 0:
            continue

        event_points.append(
            CalorieAdjustmentEventPoint(
                id=adjustment.id,
                date=_resolve_week_end_date(
                    adjustment.current_week_label,
                    adjustment.created_at.date(),
                ),
                week_label=adjustment.current_week_label,
                reference_weight=adjustment.current_week_avg,
                previous_target_calories=adjustment.previous_target_calories,
                new_target_calories=adjustment.new_target_calories,
                calorie_change=adjustment.calorie_change,
                adjustment_reason=adjustment.adjustment_reason,
                progress_status=adjustment.progress_status,
            )
        )

    return sorted(event_points, key=lambda event: event.date)


def get_adherence_overview(
    database,
    user_id: str,
    *,
    week_label: str | None = None,
) -> AdherenceOverview:
    weekly_summary = calculate_weekly_adherence_summary(
        database,
        user_id,
        week_label=week_label,
    )
    daily_breakdown: list[AdherenceDailyBreakdownPoint] = []

    for day_offset in range(7):
        target_date = weekly_summary.start_date + timedelta(days=day_offset)
        daily_summary = calculate_daily_adherence_summary(
            database,
            user_id,
            target_date=target_date,
        )
        daily_breakdown.append(
            AdherenceDailyBreakdownPoint(
                date=target_date,
                day_label=DAY_LABELS[target_date.weekday()],
                total_meals=daily_summary.total_meals,
                registered_meals=daily_summary.registered_meals,
                completed_meals=daily_summary.completed_meals,
                modified_meals=daily_summary.modified_meals,
                omitted_meals=daily_summary.omitted_meals,
                pending_meals=daily_summary.pending_meals,
                adherence_percentage=daily_summary.adherence_percentage,
            )
        )

    return AdherenceOverview(
        week_label=weekly_summary.week_label,
        start_date=weekly_summary.start_date,
        end_date=weekly_summary.end_date,
        adherence_percentage=weekly_summary.adherence_percentage,
        weekly_adherence_factor=weekly_summary.weekly_adherence_factor,
        adherence_level=weekly_summary.adherence_level,
        tracking_coverage_percentage=weekly_summary.tracking_coverage_percentage,
        total_planned_meals=weekly_summary.total_planned_meals,
        total_meals_registered=weekly_summary.total_meals_registered,
        completed_meals=weekly_summary.completed_meals,
        modified_meals=weekly_summary.modified_meals,
        omitted_meals=weekly_summary.omitted_meals,
        pending_meals=weekly_summary.pending_meals,
        interpretation_message=weekly_summary.interpretation_message,
        daily_breakdown=daily_breakdown,
    )


def get_active_diet_overview(database, user_id: str) -> ActiveDietOverview | None:
    latest_diet = get_latest_user_diet(database, user_id)
    if latest_diet is None:
        return None

    calories_per_meal = [
        ActiveDietMealOverview(
            meal_number=meal.meal_number,
            label=f"Comida {meal.meal_number}",
            target_calories=meal.target_calories,
            actual_calories=meal.actual_calories,
            target_protein_grams=meal.target_protein_grams,
            target_fat_grams=meal.target_fat_grams,
            target_carb_grams=meal.target_carb_grams,
            distribution_percentage=meal.distribution_percentage,
        )
        for meal in latest_diet.meals
    ]

    return ActiveDietOverview(
        id=latest_diet.id,
        created_at=latest_diet.created_at,
        target_calories=latest_diet.target_calories,
        protein_grams=latest_diet.protein_grams,
        fat_grams=latest_diet.fat_grams,
        carb_grams=latest_diet.carb_grams,
        meals_count=latest_diet.meals_count,
        calories_per_meal=calories_per_meal,
    )


_REGRESSION_MIN_POINTS = 3
_REGRESSION_PROJECTION_WEEKS = 4


class _RegressionResult(NamedTuple):
    points: list[RegressionTrendPoint]
    weekly_change: float | None


def compute_weight_regression(
    weight_progress_series: list[WeightProgressPoint],
) -> _RegressionResult:
    """Least-squares linear regression on actual weight entries + 4-week projection."""
    if len(weight_progress_series) < _REGRESSION_MIN_POINTS:
        return _RegressionResult(points=[], weekly_change=None)

    base_date = weight_progress_series[0].date
    xs = [(p.date - base_date).days for p in weight_progress_series]
    ys = [p.weight for p in weight_progress_series]
    n = len(xs)

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x ** 2
    if denom == 0:
        return _RegressionResult(points=[], weekly_change=None)

    slope = (n * sum_xy - sum_x * sum_y) / denom  # kg per day
    intercept = (sum_y - slope * sum_x) / n

    points: list[RegressionTrendPoint] = []

    # Fitted values for historical dates
    for entry in weight_progress_series:
        x = (entry.date - base_date).days
        fitted = round(slope * x + intercept, 2)
        points.append(RegressionTrendPoint(date=entry.date, weight=fitted, is_projection=False))

    # Projected values: weekly steps for the next N weeks
    last_date = weight_progress_series[-1].date
    last_x = xs[-1]
    for week in range(1, _REGRESSION_PROJECTION_WEEKS + 1):
        proj_date = last_date + timedelta(days=7 * week)
        x = last_x + 7 * week
        proj_weight = round(slope * x + intercept, 2)
        points.append(RegressionTrendPoint(date=proj_date, weight=proj_weight, is_projection=True))

    weekly_change = round(slope * 7, 3)
    return _RegressionResult(points=points, weekly_change=weekly_change)


def build_dashboard_overview(
    database,
    current_user: UserPublic,
) -> DashboardOverviewResponse:
    weight_entries = list_weight_entries(database, current_user.id)
    weekly_averages_for_analysis = calculate_weekly_averages(weight_entries)
    weight_progress_series = get_weight_progress_series(weight_entries)
    weekly_weight_averages = get_weekly_weight_averages(weight_entries)
    weekly_analysis = analyze_weekly_progress(current_user, weekly_averages_for_analysis)
    adherence_week_label = weekly_analysis.current_week_label if weekly_analysis.current_week_label else None
    adherence_overview = get_adherence_overview(
        database,
        current_user.id,
        week_label=adherence_week_label,
    )
    active_diet_overview = get_active_diet_overview(database, current_user.id)
    adjustment_events = get_calorie_adjustment_events(database, current_user.id)
    expected_weight_trend, expected_trend_label = get_expected_weight_trend(
        current_user,
        weight_progress_series,
        weekly_weight_averages,
    )
    regression_result = compute_weight_regression(weight_progress_series)
    nutrition_summary = _get_current_nutrition_summary(current_user)

    latest_weight = (
        weight_progress_series[-1].weight
        if weight_progress_series
        else _safe_round(current_user.current_weight)
    )
    latest_weight_date = (
        weight_progress_series[-1].date
        if weight_progress_series
        else None
    )

    current_target_calories = (
        nutrition_summary.target_calories
        if nutrition_summary is not None
        else (
            active_diet_overview.target_calories
            if active_diet_overview is not None
            else current_user.target_calories
        )
    )
    current_macros = DashboardMacroSummary(
        protein_grams=(
            nutrition_summary.protein_grams
            if nutrition_summary is not None
            else active_diet_overview.protein_grams if active_diet_overview is not None else None
        ),
        fat_grams=(
            nutrition_summary.fat_grams
            if nutrition_summary is not None
            else active_diet_overview.fat_grams if active_diet_overview is not None else None
        ),
        carb_grams=(
            nutrition_summary.carb_grams
            if nutrition_summary is not None
            else active_diet_overview.carb_grams if active_diet_overview is not None else None
        ),
    )

    summary_metrics = DashboardSummaryMetrics(
        current_weight=latest_weight,
        current_weight_date=latest_weight_date,
        latest_weekly_change=weekly_analysis.weekly_change,
        current_target_calories=_safe_round(current_target_calories),
        current_macros=current_macros,
        weekly_adherence_percentage=adherence_overview.adherence_percentage,
        weekly_adherence_factor=adherence_overview.weekly_adherence_factor,
        adherence_level=adherence_overview.adherence_level,
        adherence_interpretation=adherence_overview.interpretation_message,
        goal=current_user.goal,
    )

    return DashboardOverviewResponse(
        summary=summary_metrics,
        weight_progress=WeightProgressOverview(
            entries=weight_progress_series,
            weekly_averages=weekly_weight_averages,
            expected_trend=expected_weight_trend,
            expected_trend_label=expected_trend_label,
            regression_trend=regression_result.points,
            regression_weekly_change=regression_result.weekly_change,
            adjustment_events=adjustment_events,
            latest_analysis=weekly_analysis,
        ),
        adherence=adherence_overview,
        active_diet=active_diet_overview,
    )
